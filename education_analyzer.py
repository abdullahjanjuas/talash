"""
education_analyzer.py
=====================
Module 2: Educational Profile Analysis

Pipeline:
  1. Load & clean QS rankings CSV and Pakistani universities JSON
  2. Build alias map for fast institution lookup
  3. For each candidate:
       a. Fetch Education + Experience rows from DB
       b. Classify each degree (SSC/HSSC/UG/PG/PhD)
       c. Normalize all academic scores to 0-1 scale
       d. Score each institution (PAK JSON → QS CSV → fallback)
       e. Detect gaps between consecutive education stages
       f. Justify gaps using overlapping experience records
       g. Analyze academic progression (improving/stable/declining)
       h. Compute weighted final score
       i. Generate human-readable interpretation
  4. Return structured result dict → stored in analysis_cache table
"""

import json
import re
import numpy as np
import pandas as pd
from rapidfuzz import process, fuzz

from database import SessionLocal
from models import Education, Experience


# =============================================================================
# SECTION 1: DATA LOADING & CLEANING
# =============================================================================

def _load_qs_rankings(path="qs_rankings.csv") -> pd.DataFrame:
    """
    Load the QS World University Rankings CSV.
    Normalizes column names and converts score columns to float.
    Returns a clean DataFrame with 'institution' and 'overall_score' columns.
    """
    try:
        df = pd.read_csv(path)
    except FileNotFoundError:
        # Try alternate location
        df = pd.read_csv(f"data/{path}")

    # Strip whitespace from column names
    df.columns = df.columns.str.strip()

    # Rename to consistent internal names
    rename_map = {}
    for col in df.columns:
        if col.lower() in ("institution_name", "institution"):
            rename_map[col] = "institution"
        if col.lower() in ("overall score", "overall_score"):
            rename_map[col] = "overall_score"
    df.rename(columns=rename_map, inplace=True)

    # Convert overall_score to numeric (some entries are "-" or "N/A")
    if "overall_score" in df.columns:
        df["overall_score"] = (
            df["overall_score"]
            .astype(str)
            .str.strip()
            .replace({"-": np.nan, "NA": np.nan, "N/A": np.nan, "": np.nan})
        )
        df["overall_score"] = pd.to_numeric(df["overall_score"], errors="coerce")

    # Drop rows with no institution name
    df = df.dropna(subset=["institution"])
    df["institution"] = df["institution"].astype(str).str.strip()

    return df


def _load_pak_unis(path="pak_unis.json") -> dict:
    """Load Pakistani universities JSON with aliases and scores."""
    try:
        with open(path) as f:
            return json.load(f)
    except FileNotFoundError:
        with open(f"data/{path}") as f:
            return json.load(f)


# Load once at module import — avoids re-reading on every call
_QS_DF = _load_qs_rankings()
_PAK_DATA = _load_pak_unis()

# Pre-extract QS institution list for fuzzy matching (saves repeated .tolist() calls)
_QS_INSTITUTIONS = _QS_DF["institution"].tolist()


# =============================================================================
# SECTION 2: INSTITUTION NAME NORMALIZATION & ALIAS MAP
# =============================================================================

def _build_alias_map(pak_data: dict) -> dict:
    """
    Build a flat alias → canonical_name lookup dict.

    Example:
        "nust" → "National University of Sciences and Technology"
        "national university of sciences & technology" → same
    """
    alias_map = {}
    for canonical_name, data in pak_data.items():
        # Map the canonical name itself
        alias_map[canonical_name.lower().strip()] = canonical_name
        # Map every alias
        for alias in data.get("aliases", []):
            alias_map[alias.lower().strip()] = canonical_name
    return alias_map


_ALIAS_MAP = _build_alias_map(_PAK_DATA)


def _normalize_institution_name(raw: str) -> str:
    """
    Lowercase + strip + basic cleanup for matching.
    Removes common suffixes that confuse fuzzy matching.
    """
    if not raw:
        return ""
    name = raw.lower().strip()
    # Remove common noise words that differ between sources
    noise = [", pakistan", "- pakistan", "(pakistan)", "university of technology"]
    for n in noise:
        name = name.replace(n, "")
    return name.strip()


# =============================================================================
# SECTION 3: INSTITUTION SCORING (2-TIER LOOKUP)
# =============================================================================

def get_university_score(raw_name: str) -> tuple[float, str]:
    """
    Score an institution on a 0-1 scale using a 2-tier lookup:

    Tier 1 — Pakistani Universities JSON:
        Exact match or alias match → return pre-assigned overall_score.

    Tier 2 — QS Rankings CSV (fuzzy):
        RapidFuzz token_sort_ratio > 85 → convert QS score (0-100) to (0-1).

    Fallback:
        Unknown institution → 0.3 (neutral, not penalized heavily).

    Returns:
        (score: float, source: str)  where source ∈ {pak, qs, fallback}
    """
    if not raw_name:
        return 0.3, "fallback"

    normalized = _normalize_institution_name(raw_name)

    # --- TIER 1: Pakistani universities JSON ---
    # Direct alias match (O(1) lookup)
    if normalized in _ALIAS_MAP:
        canonical = _ALIAS_MAP[normalized]
        score = _PAK_DATA[canonical].get("overall_score", 0.3)
        return float(score), "pak"

    # Partial alias match (e.g. "nust islamabad" still hits "nust")
    for alias_key, canonical in _ALIAS_MAP.items():
        if alias_key in normalized or normalized in alias_key:
            score = _PAK_DATA[canonical].get("overall_score", 0.3)
            return float(score), "pak"

    # --- TIER 2: QS Rankings fuzzy match ---
    match_result = process.extractOne(
        normalized,
        _QS_INSTITUTIONS,
        scorer=fuzz.token_sort_ratio
    )

    if match_result and match_result[1] > 85:
        matched_name = match_result[0]
        row = _QS_DF[_QS_DF["institution"] == matched_name]
        if not row.empty:
            qs_score = row.iloc[0].get("overall_score", np.nan)
            if pd.notna(qs_score):
                # QS scores are 0-100; normalize to 0-1
                return float(qs_score) / 100.0, "qs"

    # --- FALLBACK ---
    return 0.3, "fallback"


# =============================================================================
# SECTION 4: DEGREE CLASSIFICATION
# =============================================================================

# Keywords used to classify degree level from free-text degree titles
_DEGREE_KEYWORDS = {
    "ssc":   ["ssc", "matric", "secondary school certificate", "grade 10", "class x"],
    "hssc":  ["hssc", "fsc", "fa", "inter", "higher secondary", "a-level", "a level",
              "intermediate", "class xii", "grade 12"],
    "ug":    ["bs", "bsc", "b.sc", "be", "b.e", "bcs", "bba", "bachelor",
              "b.tech", "beng", "b.eng", "undergraduate", "hons", "honours",
              "14 year", "16 year"],   # 16-year BSc exists in Pakistan
    "pg":    ["ms", "msc", "m.sc", "mphil", "m.phil", "mba", "master",
              "m.tech", "postgraduate", "post-graduate"],
    "phd":   ["phd", "ph.d", "doctorate", "doctoral"],
}


def classify_degree(degree_title: str, level_field: str = "") -> str:
    """
    Classify a degree into one of: ssc, hssc, ug, pg, phd, unknown.

    Strategy:
        1. Check the 'level' field extracted by LLM (often already labeled).
        2. If not conclusive, keyword-scan the degree title.

    Returns lowercase string: "ssc" | "hssc" | "ug" | "pg" | "phd" | "unknown"
    """
    # Combine both fields for matching
    text = f"{level_field} {degree_title}".lower().strip()

    for level, keywords in _DEGREE_KEYWORDS.items():
        for kw in keywords:
            # Word-boundary match to avoid "msc" matching "bsc"
            if re.search(r'\b' + re.escape(kw) + r'\b', text):
                return level

    return "unknown"


# =============================================================================
# SECTION 5: ACADEMIC SCORE NORMALIZATION
# =============================================================================

def normalize_academic_score(cgpa=None, percentage=None) -> float | None:
    """
    Normalize academic performance to a 0-1 scale.

    Logic:
        - CGPA on 4.0 scale  → divide by 4.0
        - CGPA on 5.0 scale  → divide by 5.0  (detected if value > 4.0)
        - CGPA on 10.0 scale → divide by 10.0 (detected if value > 5.0)
        - Percentage         → divide by 100.0
        - Both missing       → return None

    Returns None if no valid score found (so caller can skip it).
    """
    if cgpa is not None:
        try:
            val = float(cgpa)
            if val > 10.0:
                # Likely out of 100 reported as "CGPA" — treat as percentage
                return min(val / 100.0, 1.0)
            elif val > 5.0:
                return min(val / 10.0, 1.0)   # 10-point scale
            elif val > 4.0:
                return min(val / 5.0, 1.0)    # 5-point scale
            else:
                return min(val / 4.0, 1.0)    # standard 4-point scale
        except (ValueError, TypeError):
            pass

    if percentage is not None:
        try:
            val = float(str(percentage).replace("%", "").strip())
            return min(val / 100.0, 1.0)
        except (ValueError, TypeError):
            pass

    return None


# =============================================================================
# SECTION 6: GAP DETECTION & JUSTIFICATION
# =============================================================================

def _safe_year(raw) -> int | None:
    """Extract 4-digit year from various formats: '2018', '2018-2019', '2018/19'."""
    if not raw:
        return None
    try:
        # Take first 4 characters that look like a year
        match = re.search(r'\b(19|20)\d{2}\b', str(raw))
        return int(match.group()) if match else None
    except:
        return None


def detect_gaps(edu_records: list) -> list[dict]:
    """
    Detect gaps between consecutive education stages.

    Algorithm:
        1. Sort records by start_year ascending.
        2. For each consecutive pair, compute: gap = next.start - prev.end
        3. If gap > 1 year → flag it.

    Returns list of gap dicts:
        {from_year, to_year, duration_years, between: (prev_degree, next_degree)}
    """
    # Filter records that have parseable years
    dated = []
    for e in edu_records:
        sy = _safe_year(e.start_year)
        ey = _safe_year(e.end_year)
        if sy:
            dated.append((sy, ey, e.degree or "Unknown"))

    # Sort by start year
    dated.sort(key=lambda x: x[0])

    gaps = []
    for i in range(1, len(dated)):
        prev_end = dated[i-1][1]
        curr_start = dated[i][0]

        if prev_end and curr_start:
            gap = curr_start - prev_end
            if gap > 1:
                gaps.append({
                    "from_year": prev_end,
                    "to_year": curr_start,
                    "duration_years": gap,
                    "between": (dated[i-1][2], dated[i][2])
                })

    return gaps


def justify_gaps(gaps: list[dict], exp_records: list) -> list[dict]:
    """
    Check if each detected gap overlaps with documented professional activity.

    For each gap window [from_year, to_year]:
        Parse experience start/end years.
        If any experience overlaps the gap window → mark as justified.

    Returns the same gap list with 'justified' bool and 'justification' string added.
    """
    # Build experience year ranges
    exp_ranges = []
    for ex in exp_records:
        s = _safe_year(ex.start_date)
        e = _safe_year(ex.end_date) or 9999  # ongoing = treat as present
        if s:
            exp_ranges.append((s, e, ex.title or "Professional activity"))

    for gap in gaps:
        g_from = gap["from_year"]
        g_to = gap["to_year"]
        justified = False
        justification = ""

        for (es, ee, etitle) in exp_ranges:
            # Overlap: experience starts before gap ends AND ends after gap starts
            if es <= g_to and ee >= g_from:
                justified = True
                justification = etitle
                break

        gap["justified"] = justified
        gap["justification"] = justification if justified else "No professional activity found"

    return gaps


# =============================================================================
# SECTION 7: ACADEMIC PROGRESSION ANALYSIS
# =============================================================================

def analyze_progression(edu_records: list) -> str:
    """
    Analyze whether academic scores improved, declined, or stayed stable
    across educational stages (ordered by start_year).

    Strategy:
        - Collect (start_year, normalized_score) pairs.
        - Need at least 2 data points to judge.
        - Compare last score vs first score.

    Returns: "improving" | "declining" | "stable" | "insufficient_data"
    """
    scored = []
    for e in sorted(edu_records, key=lambda x: _safe_year(x.start_year) or 0):
        score = normalize_academic_score(e.cgpa, e.percentage)
        if score is not None:
            scored.append(score)

    if len(scored) < 2:
        return "insufficient_data"

    delta = scored[-1] - scored[0]

    if delta > 0.05:
        return "improving"
    elif delta < -0.05:
        return "declining"
    else:
        return "stable"


# =============================================================================
# SECTION 8: MAIN ANALYSIS PIPELINE
# =============================================================================

def analyze_education(candidate_id: int) -> dict:
    """
    Full educational profile analysis for a single candidate.

    Steps:
        1. Fetch Education and Experience records from DB.
        2. Classify each degree (ssc/hssc/ug/pg/phd).
        3. Score each institution via 2-tier lookup.
        4. Normalize all academic scores.
        5. Detect and justify educational gaps.
        6. Analyze academic progression.
        7. Compute weighted final score.
        8. Build and return result dict.

    Returns {} if no education records found.
    """
    db = SessionLocal()

    try:
        edu_records = db.query(Education).filter(
            Education.candidate_id == candidate_id
        ).all()

        exp_records = db.query(Experience).filter(
            Experience.candidate_id == candidate_id
        ).all()
    finally:
        db.close()

    if not edu_records:
        return {}

    # -------------------------
    # 2. Classify every degree
    # -------------------------
    classified = []
    for e in edu_records:
        level = classify_degree(e.degree or "", e.level or "")
        classified.append((e, level))

    # Count by level
    level_counts = {
        "ssc": 0, "hssc": 0, "ug": 0, "pg": 0, "phd": 0, "unknown": 0
    }
    for _, lvl in classified:
        level_counts[lvl] = level_counts.get(lvl, 0) + 1

    # -------------------------
    # 3. Institution scoring
    # -------------------------
    uni_scores = []
    uni_details = []  # for transparency in result

    for e, lvl in classified:
        score, source = get_university_score(e.institution)
        uni_scores.append(score)
        uni_details.append({
            "institution": e.institution,
            "degree": e.degree,
            "level": lvl,
            "score": round(score, 3),
            "source": source
        })

    avg_uni_score = sum(uni_scores) / len(uni_scores) if uni_scores else 0.3

    # -------------------------
    # 4. Academic score normalization
    # -------------------------
    academic_scores = []
    for e, _ in classified:
        s = normalize_academic_score(e.cgpa, e.percentage)
        if s is not None:
            academic_scores.append(s)

    avg_academic_score = (
        sum(academic_scores) / len(academic_scores)
        if academic_scores else None
    )

    # -------------------------
    # 5. Gap detection + justification
    # -------------------------
    raw_gaps = detect_gaps(edu_records)
    justified_gaps = justify_gaps(raw_gaps, exp_records)

    unjustified_count = sum(1 for g in justified_gaps if not g["justified"])
    total_gap_years = sum(g["duration_years"] for g in justified_gaps)

    # Gap penalty: 0.05 per unjustified gap, capped at 0.3
    gap_penalty = min(unjustified_count * 0.05 + (total_gap_years * 0.01), 0.3)

    all_justified = unjustified_count == 0

    # -------------------------
    # 6. Progression analysis
    # -------------------------
    progression = analyze_progression(edu_records)

    progression_score = {
        "improving": 1.0,
        "stable": 0.7,
        "declining": 0.3,
        "insufficient_data": 0.5
    }.get(progression, 0.5)

    # -------------------------
    # 7. Weighted final score
    # -------------------------
    # Weights: University quality 40%, Academic performance 30%,
    #          Progression 20%, Gap penalty 10%
    academic_component = avg_academic_score if avg_academic_score is not None else 0.5

    final_score = (
        0.40 * avg_uni_score +
        0.30 * academic_component +
        0.20 * progression_score +
        0.10 * (1.0 - gap_penalty)
    )
    final_score = round(min(final_score, 1.0), 3)

    # -------------------------
    # 8. Human-readable interpretation
    # -------------------------
    if final_score >= 0.80:
        interpretation = "Excellent academic profile — top institutions, strong performance, consistent progression."
    elif final_score >= 0.65:
        interpretation = "Strong academic profile — good institutional quality with solid academic record."
    elif final_score >= 0.50:
        interpretation = "Moderate academic profile — decent foundations; some areas could be stronger."
    elif final_score >= 0.35:
        interpretation = "Below-average profile — limited institutional recognition or weaker academic scores."
    else:
        interpretation = "Weak academic profile — significant gaps, low scores, or unrecognized institutions."

    # -------------------------
    # Build result dict
    # -------------------------
    return {
        # Counts
        "ssc_count":  level_counts["ssc"],
        "hssc_count": level_counts["hssc"],
        "ug_count":   level_counts["ug"],
        "pg_count":   level_counts["pg"],
        "phd_count":  level_counts["phd"],

        # Scores
        "avg_university_score": round(avg_uni_score, 3),
        "avg_academic_score":   round(avg_academic_score, 3) if avg_academic_score else None,
        "final_score":          final_score,

        # Details
        "institution_details": uni_details,
        "progression":         progression,
        "gaps":                justified_gaps,
        "total_gap_years":     total_gap_years,
        "justified_gaps":      all_justified,

        # Interpretation
        "interpretation": interpretation,
    }