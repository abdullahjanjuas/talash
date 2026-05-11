# candidate_ranker.py
# Extra Credit: Full-Scale Quantifiable Candidate Ranking Module
#
# PIPELINE:
#   1. Load all AnalysisCache records for every candidate
#   2. Extract sub-scores from each module's cached result
#   3. Apply the official TALASH weighting formula to compute a total_score
#   4. Rank all candidates by total_score descending
#   5. Return a sorted list of ranked candidate dicts
#
# WEIGHTING FORMULA (designed to match rubric priorities):
#
#   Education Profile    → 15% of total
#   Research Profile     → 30% of total
#     ├─ Journal Score       12%
#     ├─ Conference Score     8%
#     └─ Topic/Coauthor       10%
#   Supervision/Books/Patents →  8%
#   Experience Profile   → 30% of total
#   Skill Profile        → 17% of total
#
# Each sub-score is a 0–1 float from its respective analyzer.
# The final total_score is also 0–1, displayed as a percentage.

import json
from database import SessionLocal
from models import Candidate, AnalysisCache


# ---------------------------------------------------------------------------
# MODULE WEIGHTS (must sum to 1.0)
# ---------------------------------------------------------------------------

WEIGHTS = {
    "education":      0.15,
    "journal":        0.12,
    "conference":     0.08,
    "topic_coauthor": 0.10,
    "supervision":    0.08,
    "experience":     0.30,
    "skills":         0.17,
}


# ---------------------------------------------------------------------------
# SECTION 1 — SCORE EXTRACTION HELPERS
# ---------------------------------------------------------------------------

def _safe_float(value, default=0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _extract_education_score(cache_json: str) -> float:
    data = json.loads(cache_json)
    return _safe_float(data.get("final_score", 0.0))


def _extract_journal_score(cache_json: str) -> float:
    data = json.loads(cache_json)
    if not data.get("has_data"):
        return 0.0
    return _safe_float(data.get("journal_score", 0.0))


def _extract_conference_score(cache_json: str) -> float:
    data = json.loads(cache_json)
    if not data.get("has_data"):
        return 0.0
    return _safe_float(data.get("conference_score", 0.0))


def _extract_topic_coauthor_score(cache_json: str) -> float:
    data = json.loads(cache_json)
    if not data.get("has_data"):
        return 0.0
    d = _safe_float(data.get("diversity_score", 0.0))
    c = _safe_float(data.get("collaboration_score", 0.0))
    # Balanced combination
    return round(0.5 * d + 0.5 * c, 3)


def _extract_supervision_score(cache_json: str) -> float:
    data = json.loads(cache_json)
    return _safe_float(data.get("combined_score", 0.0))


def _extract_experience_score(cache_json: str) -> float:
    data = json.loads(cache_json)
    if not data.get("has_data"):
        return 0.0
    return _safe_float(data.get("final_score", 0.0))


def _extract_skill_score(cache_json: str) -> float:
    data = json.loads(cache_json)
    if not data.get("has_data"):
        return 0.0
    return _safe_float(data.get("skill_score", 0.0))


# Map module names → extractor functions
EXTRACTORS = {
    "education_profile":          _extract_education_score,
    "journal_profile":            _extract_journal_score,
    "conference_profile":         _extract_conference_score,
    "topic_coauthor_profile":     _extract_topic_coauthor_score,
    "supervision_books_patents":  _extract_supervision_score,
    "experience_profile":         _extract_experience_score,
    "skill_profile":              _extract_skill_score,
}

# Map module → WEIGHTS key
MODULE_TO_WEIGHT_KEY = {
    "education_profile":          "education",
    "journal_profile":            "journal",
    "conference_profile":         "conference",
    "topic_coauthor_profile":     "topic_coauthor",
    "supervision_books_patents":  "supervision",
    "experience_profile":         "experience",
    "skill_profile":              "skills",
}


# ---------------------------------------------------------------------------
# SECTION 2 — PER-CANDIDATE SCORE COMPUTATION
# ---------------------------------------------------------------------------

def compute_candidate_score(candidate_id: int) -> dict:
    """
    Compute the full weighted score for a single candidate from their cached analyses.
    Returns a dict with sub-scores and total_score.
    """
    db = SessionLocal()
    try:
        cache_records = db.query(AnalysisCache).filter(
            AnalysisCache.candidate_id == candidate_id
        ).all()
    finally:
        db.close()

    # Build a module → cache_json lookup
    module_cache = {r.module: r.result_json for r in cache_records}

    sub_scores = {}
    weighted_sum = 0.0
    total_weight_applied = 0.0

    for module_name, extractor in EXTRACTORS.items():
        weight_key = MODULE_TO_WEIGHT_KEY[module_name]
        weight     = WEIGHTS[weight_key]

        if module_name in module_cache:
            try:
                score = extractor(module_cache[module_name])
            except Exception:
                score = 0.0
        else:
            score = 0.0  # module not yet run

        sub_scores[weight_key] = round(score, 3)
        weighted_sum += weight * score
        total_weight_applied += weight

    # Normalize in case some modules are missing
    if total_weight_applied > 0:
        total_score = weighted_sum / total_weight_applied
    else:
        total_score = 0.0

    return {
        "candidate_id": candidate_id,
        "sub_scores": sub_scores,
        "total_score": round(total_score, 4),
        "total_score_pct": round(total_score * 100, 1)
    }


# ---------------------------------------------------------------------------
# SECTION 3 — FULL RANKING TABLE
# ---------------------------------------------------------------------------

def rank_all_candidates() -> list:
    """
    Rank every candidate in the database by their total_score.
    Returns a list of dicts sorted by total_score descending.
    Each dict has: rank, candidate_id, name, email, total_score_pct, sub_scores,
    and a suitability_label.
    """
    db = SessionLocal()
    try:
        candidates = db.query(Candidate).all()
    finally:
        db.close()

    scored = []
    for c in candidates:
        result = compute_candidate_score(c.id)
        scored.append({
            "candidate_id": c.id,
            "name": c.name or f"Candidate #{c.id}",
            "email": c.email or "—",
            "cv_filename": c.cv_filename or "—",
            **result
        })

    # Sort descending by total_score
    scored.sort(key=lambda x: x["total_score"], reverse=True)

    # Assign rank and suitability label
    for i, s in enumerate(scored, 1):
        s["rank"] = i
        pct = s["total_score_pct"]
        if pct >= 75:
            s["suitability"] = "Highly Recommended"
        elif pct >= 55:
            s["suitability"] = "Recommended"
        elif pct >= 35:
            s["suitability"] = "Consider"
        else:
            s["suitability"] = "Below Threshold"

    return scored


# ---------------------------------------------------------------------------
# SECTION 4 — SUMMARY REPORT GENERATOR
# ---------------------------------------------------------------------------

def generate_candidate_summary(candidate_id: int) -> str:
    """
    Generate a plain-text narrative summary of a candidate's profile
    by reading all cached analysis results. This is the 'candidate summary
    generation' requirement from the rubric.
    """
    db = SessionLocal()
    try:
        candidate = db.query(Candidate).filter(Candidate.id == candidate_id).first()
        cache_records = db.query(AnalysisCache).filter(
            AnalysisCache.candidate_id == candidate_id
        ).all()
    finally:
        db.close()

    if not candidate:
        return "Candidate not found."

    module_cache = {r.module: json.loads(r.result_json) for r in cache_records}
    score_data   = compute_candidate_score(candidate_id)
    sub          = score_data["sub_scores"]

    name  = candidate.name or "This candidate"
    lines = [f"CANDIDATE SUMMARY REPORT: {name}",
             "=" * 55]

    # Overall score
    lines.append(f"\nOverall Score: {score_data['total_score_pct']}% — {_suitability_from_pct(score_data['total_score_pct'])}")

    # Education
    edu = module_cache.get("education_profile", {})
    if edu:
        lines.append(f"\nEDUCATION  (score: {sub.get('education', 0):.2f})")
        lines.append(f"   University Score: {edu.get('avg_university_score', 0):.2f} | "
                     f"Academic Score: {(edu.get('avg_academic_score') or 0):.2f}")
        lines.append(f"   Progression: {edu.get('progression', '—')} | Gaps: {len(edu.get('gaps', []))}")
        lines.append(f"   Interpretation: {edu.get('interpretation', '—')}")

    # Experience
    exp = module_cache.get("experience_profile", {})
    if exp and exp.get("has_data"):
        lines.append(f"\nEXPERIENCE  (score: {sub.get('experience', 0):.2f})")
        lines.append(f"   Total Roles: {exp.get('total_roles', 0)} | "
                     f"Trajectory: {exp.get('trajectory', '—').capitalize()}")
        lines.append(f"   Unexplained Gaps: {exp.get('unexplained_gaps_count', 0)} | "
                     f"Suspicious Overlaps: {exp.get('suspicious_overlaps_count', 0)}")
        lines.append(f"   Interpretation: {exp.get('interpretation', '—')}")

    # Research: Journals
    jrn = module_cache.get("journal_profile", {})
    if jrn and jrn.get("has_data"):
        s = jrn.get("summary", {})
        lines.append(f"\nJOURNALS  (score: {sub.get('journal', 0):.2f})")
        lines.append(f"   Total: {s.get('total_journal_papers', 0)} | "
                     f"WoS: {s.get('wos_count', 0)} | Scopus: {s.get('scopus_count', 0)} | "
                     f"Q1: {s.get('q1_count', 0)}")
        lines.append(f"   {s.get('overall_interpretation', '—')[:150]}")

    # Research: Conferences
    conf = module_cache.get("conference_profile", {})
    if conf and conf.get("has_data"):
        s = conf.get("summary", {})
        lines.append(f"\nCONFERENCES  (score: {sub.get('conference', 0):.2f})")
        lines.append(f"   Total: {s.get('total_conference_papers', 0)} | "
                     f"A*: {s.get('a_star_count', 0)} | First Author: {s.get('first_author_count', 0)}")
        lines.append(f"   {s.get('overall_interpretation', '—')[:150]}")

    # Topic + Coauthor
    tc = module_cache.get("topic_coauthor_profile", {})
    if tc and tc.get("has_data"):
        ta = tc.get("topic_analysis", {})
        ca = tc.get("coauthor_analysis", {})
        lines.append(f"\nRESEARCH DIVERSITY  (score: {sub.get('topic_coauthor', 0):.2f})")
        lines.append(f"   Dominant Topic: {ta.get('dominant_topic', '—')} | "
                     f"Diversity: {ta.get('diversity_label', '—')} ({tc.get('diversity_score', 0):.2f})")
        lines.append(f"   Co-authors: {ca.get('total_unique_coauthors', 0)} unique | "
                     f"Avg team size: {ca.get('avg_team_size', 0):.1f}")

    # Supervision/Books/Patents
    sbp = module_cache.get("supervision_books_patents", {})
    if sbp:
        sup = sbp.get("supervision", {})
        lines.append(f"\nSUPERVISION / BOOKS / PATENTS  (score: {sub.get('supervision', 0):.2f})")
        lines.append(f"   PhD supervised: {sup.get('phd_main', 0)} | MS supervised: {sup.get('ms_main', 0)}")
        lines.append(f"   Books: {len(sbp.get('books', []))} | Patents: {len(sbp.get('patents', []))}")
        lines.append(f"   {sbp.get('interpretation', '—')}")

    # Skills
    sk = module_cache.get("skill_profile", {})
    if sk and sk.get("has_data"):
        s = sk.get("summary", {})
        lines.append(f"\nSKILLS  (score: {sub.get('skills', 0):.2f})")
        lines.append(f"   Total Skills: {s.get('total_skills', 0)} | "
                     f"Strongly Evidenced: {s.get('strongly_evidenced_count', 0)} | "
                     f"Unsupported: {s.get('unsupported_count', 0)}")
        if s.get("top_evidenced_skills"):
            lines.append(f"   Top Skills: {', '.join(s['top_evidenced_skills'][:5])}")
        lines.append(f"   {s.get('overall_interpretation', '—')[:150]}")

    lines.append("\n" + "=" * 55)
    return "\n".join(lines)


def _suitability_from_pct(pct: float) -> str:
    if pct >= 75:   return "Highly Recommended"
    if pct >= 55:   return "Recommended"
    if pct >= 35:   return "Consider"
    return "Below Threshold"
