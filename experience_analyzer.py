# Module 3.8: Professional Experience and Employment History Analysis
# PIPELINE OVERVIEW:
#   1. Load Education + Experience records from DB for a given candidate_id
#   2. Parse all raw date strings into (year, month) tuples for arithmetic
#   3. Detect overlaps: Experience vs Experience, Education vs Experience
#   4. Detect professional gaps (post-education and between jobs)
#   5. Justify gaps using education periods or explicit CV signals
#   6. Analyze career progression via seniority tier scoring
#   7. Detect missing critical information and draft a follow-up email
#   8. Compute a weighted final_score and return the full result dict

from database import SessionLocal
from models import Education, Experience, Candidate
from datetime import datetime
import re


# SECTION 1: DATE PARSING
# CV dates arrive as raw strings: "Jan 2020", "2020-03", "March 2019",
# "Present", "Ongoing", "2022", etc. We must normalize all of them to
# (year, month) integer tuples before any arithmetic comparison is possible.

MONTH_MAP = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
    "january": 1, "february": 2, "march": 3, "april": 4,
    "june": 6, "july": 7, "august": 8, "september": 9,
    "october": 10, "november": 11, "december": 12
}

PRESENT_KEYWORDS = {"present", "ongoing", "current", "now", "till date", "to date", "till now"}


def parse_date(date_str: str, is_end: bool = False):
    """
    Convert a raw CV date string to a (year, month) tuple.

    is_end=True means this is an end date:
      - "Present"/"Ongoing" → today's (year, month)
      - Missing month on end dates defaults to December (conservative: 
        maximizes the period, meaning we give benefit of the doubt on gaps)

    is_end=False means this is a start date:
      - Missing month defaults to January

    Returns None if parsing completely fails (e.g. empty string, null).
    """
    if not date_str:
        return None

    date_str = str(date_str).strip().lower()

    # Check for "present" / "ongoing" / "current" variants
    if date_str in PRESENT_KEYWORDS:
        now = datetime.now()
        return (now.year, now.month)

    # Try to extract a 4-digit year first — it's always present
    year_match = re.search(r'\b(19|20)\d{2}\b', date_str)
    if not year_match:
        return None
    year = int(year_match.group())

    # Try to find a month name or number
    month = None

    # Check for month names
    for month_name, month_num in MONTH_MAP.items():
        if month_name in date_str:
            month = month_num
            break

    # Check for numeric month: "2020-03" or "03/2020"
    if month is None:
        num_match = re.search(r'\b(0?[1-9]|1[0-2])\b', date_str)
        if num_match:
            candidate_month = int(num_match.group())
            # Make sure we're not picking up the year itself
            if candidate_month != year:
                month = candidate_month

    # Default month if not found
    if month is None:
        month = 12 if is_end else 1

    return (year, month)


def date_to_months(ym_tuple):
    """
    Convert (year, month) to total months since year 0.
    This gives us a single integer we can subtract for gap arithmetic.
    E.g.: (2020, 6) → 2020*12 + 6 = 24246
    """
    if ym_tuple is None:
        return None
    return ym_tuple[0] * 12 + ym_tuple[1]


# SECTION 2: SENIORITY TIER MAPPING (for career progression)\
# We map job titles to a 4-level seniority tier.
# Keywords are checked via substring matching (case-insensitive).
# Higher tier = more senior. Tier is determined by the HIGHEST matching keyword.

SENIORITY_TIERS = [
    # Check Junior FIRST — "intern/trainee/junior" always overrides base title
    (1, "Junior",     ["intern", "trainee", "junior", "apprentice",
                       "student", "graduate", "entry level", "entry-level"]),

    (4, "Executive",  ["ceo", "cto", "coo", "cfo", "vp ", "vice president",
                       "director", "dean", "rector", "provost", "chairman"]),
    (3, "Senior",     ["professor", "associate professor", "senior", "lead",
                       "principal", "head", "manager", "supervisor",
                       "team lead", "architect", "consultant"]),
    (2, "Mid-Level",  ["engineer", "developer", "analyst", "researcher",
                       "lecturer", "instructor", "associate", "specialist",
                       "coordinator", "officer", "executive"]),
]


def get_seniority_tier(title: str):
    if not title:
        return (0, "Unknown")

    title_lower = title.lower()

    for tier_level, tier_label, keywords in SENIORITY_TIERS:
        for kw in keywords:
            if kw in title_lower:
                return (tier_level, tier_label)

    return (0, "Unknown")


# SECTION 3: OVERLAP DETECTION
# Standard interval overlap test:
# Two intervals [A_start, A_end] and [B_start, B_end] overlap iff:
#   A_start <= B_end  AND  B_start <= A_end
#
# We work in "total months" integers (from date_to_months) so the comparison
# is just integer arithmetic.

def intervals_overlap(start_a, end_a, start_b, end_b):
    """
    Returns True if [start_a, end_a] overlaps [start_b, end_b].
    All arguments are month-integers from date_to_months().
    None values mean unknown — we return False (give benefit of the doubt).
    """
    if any(x is None for x in [start_a, end_a, start_b, end_b]):
        return False
    return start_a <= end_b and start_b <= end_a


def detect_exp_overlaps(experiences: list) -> list:
    """
    Find all pairs of experience records that overlap in time.
    Returns a list of overlap dicts describing each detected overlap.

    We do an O(n²) pairwise comparison — n is small (CV has ~5-15 jobs),
    so this is fine.
    """
    overlaps = []

    # Pre-parse all dates once
    parsed = []
    for exp in experiences:
        start = date_to_months(parse_date(exp.start_date, is_end=False))
        end   = date_to_months(parse_date(exp.end_date,   is_end=True))
        parsed.append((exp, start, end))

    # Pairwise comparison
    for i in range(len(parsed)):
        for j in range(i + 1, len(parsed)):
            exp_a, start_a, end_a = parsed[i]
            exp_b, start_b, end_b = parsed[j]

            if intervals_overlap(start_a, end_a, start_b, end_b):
                # Calculate overlap duration in months
                overlap_start = max(start_a, start_b) if (start_a and start_b) else None
                overlap_end   = min(end_a,   end_b)   if (end_a   and end_b)   else None
                duration_months = (overlap_end - overlap_start + 1) if (overlap_start and overlap_end) else None

                # Assess suspicion level
                # Full-time + full-time overlap is suspicious
                type_a = (exp_a.emp_type or "").lower()
                type_b = (exp_b.emp_type or "").lower()
                both_fulltime = ("full" in type_a and "full" in type_b)
                suspicion = "high" if both_fulltime else "low"

                overlaps.append({
                    "job_a": exp_a.title or "Unknown",
                    "org_a": exp_a.organization or "Unknown",
                    "job_b": exp_b.title or "Unknown",
                    "org_b": exp_b.organization or "Unknown",
                    "duration_months": duration_months,
                    "suspicion": suspicion,
                    "note": (
                        "Both full-time roles — requires clarification."
                        if both_fulltime
                        else "Possible concurrent/consulting role — likely legitimate."
                    )
                })

    return overlaps


def detect_edu_exp_overlaps(educations: list, experiences: list) -> list:
    """
    Find experience records that overlap with formal education periods.

    WHY: A full-time job during a full-time BS/MS could indicate:
      (a) legitimate part-time/RA work during studies, OR
      (b) an inconsistency in dates that needs clarification.

    We report the overlap and classify it — we do NOT automatically penalize.
    """
    overlaps = []

    for edu in educations:
        # Education periods are year-only — parse them as dates
        edu_start = date_to_months(parse_date(str(edu.start_year), is_end=False)) if edu.start_year else None
        edu_end   = date_to_months(parse_date(str(edu.end_year),   is_end=True))  if edu.end_year   else None

        if not edu_start or not edu_end:
            continue

        for exp in experiences:
            exp_start = date_to_months(parse_date(exp.start_date, is_end=False))
            exp_end   = date_to_months(parse_date(exp.end_date,   is_end=True))

            if intervals_overlap(edu_start, edu_end, exp_start, exp_end):
                emp_type = (exp.emp_type or "").lower()

                # Part-time / research / teaching during study = normal
                is_likely_ok = any(kw in emp_type for kw in
                                   ["part", "research", "teach", "ra", "ta",
                                    "assistant", "intern", "freelance"])

                overlaps.append({
                    "degree": edu.degree or "Unknown Degree",
                    "institution": edu.institution or "Unknown",
                    "job": exp.title or "Unknown",
                    "organization": exp.organization or "Unknown",
                    "emp_type": exp.emp_type or "Not specified",
                    "assessment": (
                        "Likely legitimate (part-time/RA/teaching during studies)"
                        if is_likely_ok
                        else "Requires clarification — full-time role during formal study"
                    )
                })

    return overlaps


# =============================================================================
# SECTION 4: GAP DETECTION
# =============================================================================

GAP_THRESHOLD_MONTHS = 6   # gaps shorter than this are ignored (job searching is normal)


def detect_professional_gaps(experiences: list, educations: list) -> list:
    """
    Detect unexplained periods where the candidate has no recorded employment.

    Two types of gaps:
      A) Between the END of formal education and the START of first job
         (entry-into-workforce gap)
      B) Between END of job[i] and START of job[i+1]
         (between-jobs gap)

    For each gap we check: was the candidate studying during this period?
    If yes → gap is "justified_by_education". Otherwise → "unexplained".
    """
    gaps = []

    if not experiences:
        return gaps

    # Parse and sort all experience records by start date
    exp_parsed = []
    for exp in experiences:
        start = parse_date(exp.start_date, is_end=False)
        end   = parse_date(exp.end_date,   is_end=True)
        if start:   # only include if we have at least a start date
            exp_parsed.append((exp, start, end))

    exp_parsed.sort(key=lambda x: date_to_months(x[1]) or 0)

    # Parse education end years (for gap justification check)
    edu_periods = []
    for edu in educations:
        edu_start_raw = parse_date(str(edu.start_year), is_end=False) if edu.start_year else None
        edu_end_raw   = parse_date(str(edu.end_year),   is_end=True)  if edu.end_year   else None
        if edu_start_raw and edu_end_raw:
            edu_periods.append((
                date_to_months(edu_start_raw),
                date_to_months(edu_end_raw),
                edu.degree or "Unknown Degree"
            ))

    def is_gap_in_education(gap_start_m, gap_end_m):
        """
        Return the degree name if the candidate was studying during this gap,
        otherwise return None.
        """
        for edu_s, edu_e, degree in edu_periods:
            if intervals_overlap(gap_start_m, gap_end_m, edu_s, edu_e):
                return degree
        return None

    # --- GAP TYPE A: Last education → First job ---
    if educations and exp_parsed:
        # Find latest education end date
        edu_ends = []
        for edu in educations:
            if edu.end_year:
                ym = parse_date(str(edu.end_year), is_end=True)
                if ym:
                    edu_ends.append(date_to_months(ym))

        if edu_ends:
            last_edu_end_m = max(edu_ends)
            first_exp_start_m = date_to_months(exp_parsed[0][1])

            if first_exp_start_m and first_exp_start_m > last_edu_end_m:
                gap_months = first_exp_start_m - last_edu_end_m
                if gap_months > GAP_THRESHOLD_MONTHS:
                    justification = is_gap_in_education(last_edu_end_m, first_exp_start_m)
                    gaps.append({
                        "type": "entry_gap",
                        "duration_months": gap_months,
                        "description": f"Gap of ~{gap_months} months between end of education and first job",
                        "justified": justification is not None,
                        "justification": f"Candidate was enrolled in {justification}" if justification else "No recorded activity during this period"
                    })

    # --- GAP TYPE B: Between consecutive jobs ---
    for i in range(len(exp_parsed) - 1):
        _, _, end_a = exp_parsed[i]
        _, start_b, _ = exp_parsed[i + 1]
        exp_a = exp_parsed[i][0]
        exp_b = exp_parsed[i + 1][0]

        end_a_m   = date_to_months(end_a)
        start_b_m = date_to_months(start_b)

        if end_a_m is None or start_b_m is None:
            continue

        if start_b_m > end_a_m:
            gap_months = start_b_m - end_a_m
            if gap_months > GAP_THRESHOLD_MONTHS:
                justification = is_gap_in_education(end_a_m, start_b_m)
                gaps.append({
                    "type": "between_jobs",
                    "duration_months": gap_months,
                    "after_job": f"{exp_a.title or 'Unknown'} @ {exp_a.organization or 'Unknown'}",
                    "before_job": f"{exp_b.title or 'Unknown'} @ {exp_b.organization or 'Unknown'}",
                    "description": f"Gap of ~{gap_months} months between consecutive roles",
                    "justified": justification is not None,
                    "justification": f"Candidate was enrolled in {justification}" if justification else "No recorded activity during this period"
                })

    return gaps


# SECTION 5: CAREER PROGRESSION ANALYSIS

def analyze_career_progression(experiences: list) -> dict:
    """
    Evaluate whether the candidate's career shows an upward trajectory.

    Process:
      1. Parse start dates and sort experiences chronologically
      2. Map each job title to a seniority tier (1–4)
      3. Analyze the tier sequence: is it generally non-decreasing?
      4. Return trajectory label + per-job tier breakdown

    Trajectory labels:
      "improving": tier sequence is non-decreasing throughout
      "stable": all roles at the same tier
      "mixed": some upward, some downward movements
      "declining": tier sequence is generally decreasing
      "unknown": fewer than 2 parseable roles
    """
    if not experiences:
        return {
            "trajectory": "unknown",
            "reason": "No experience records found",
            "roles_analyzed": [],
            "progression_score": 0.5
        }

    # Parse start dates and attach tier
    roles = []
    for exp in experiences:
        start_ym = parse_date(exp.start_date, is_end=False)
        start_m  = date_to_months(start_ym) if start_ym else None
        tier, tier_label = get_seniority_tier(exp.title)
        roles.append({
            "title": exp.title or "Unknown",
            "organization": exp.organization or "Unknown",
            "start_date": exp.start_date or "Unknown",
            "tier": tier,
            "tier_label": tier_label,
            "sort_key": start_m or 0
        })

    # Sort chronologically
    roles.sort(key=lambda r: r["sort_key"])

    if len(roles) < 2:
        return {
            "trajectory": "unknown",
            "reason": "Only one experience record — cannot assess progression",
            "roles_analyzed": roles,
            "progression_score": 0.5
        }

    # Analyze the tier sequence
    tiers = [r["tier"] for r in roles if r["tier"] > 0]

    if len(tiers) < 2:
        return {
            "trajectory": "unknown",
            "reason": "Job titles could not be classified — insufficient keywords",
            "roles_analyzed": roles,
            "progression_score": 0.5
        }

    upward_moves   = sum(1 for i in range(1, len(tiers)) if tiers[i] > tiers[i-1])
    downward_moves = sum(1 for i in range(1, len(tiers)) if tiers[i] < tiers[i-1])
    lateral_moves  = sum(1 for i in range(1, len(tiers)) if tiers[i] == tiers[i-1])
    total_moves    = len(tiers) - 1

    if upward_moves == total_moves:
        trajectory = "improving"
        progression_score = 1.0
    elif downward_moves == total_moves:
        trajectory = "declining"
        progression_score = 0.2
    elif tiers[0] == tiers[-1] and upward_moves == 0:
        trajectory = "stable"
        progression_score = 0.6
    else:
        trajectory = "mixed"
        # Score based on ratio of upward moves
        progression_score = 0.4 + 0.4 * (upward_moves / total_moves)

    return {
        "trajectory": trajectory,
        "upward_moves": upward_moves,
        "downward_moves": downward_moves,
        "lateral_moves": lateral_moves,
        "roles_analyzed": roles,
        "progression_score": round(progression_score, 2)
    }


# SECTION 6: MISSING INFORMATION DETECTION + EMAIL DRAFT

def detect_missing_info(candidate, experiences: list) -> dict:
    """
    Identify which critical fields are absent from the experience records.

    Critical fields: start_date, end_date, organization, emp_type (employment type).
    
    Returns:
      missing_fields: list of specific missing items
      completeness_score: float 0–1
      email_draft: string — a ready-to-send email if info is missing
    """
    missing_items = []
    total_fields  = 0
    filled_fields = 0

    for i, exp in enumerate(experiences, 1):
        role_label = f"Role #{i} ({exp.title or 'Untitled'})"

        # start_date
        total_fields += 1
        if not exp.start_date or str(exp.start_date).strip() in ["", "None", "null"]:
            missing_items.append(f"{role_label}: start date missing")
        else:
            filled_fields += 1

        # end_date
        total_fields += 1
        if not exp.end_date or str(exp.end_date).strip() in ["", "None", "null"]:
            missing_items.append(f"{role_label}: end date missing")
        else:
            filled_fields += 1

        # organization
        total_fields += 1
        if not exp.organization or str(exp.organization).strip() in ["", "None", "null"]:
            missing_items.append(f"{role_label}: organization/employer name missing")
        else:
            filled_fields += 1

        # emp_type
        total_fields += 1
        if not exp.emp_type or str(exp.emp_type).strip() in ["", "None", "null"]:
            missing_items.append(f"{role_label}: employment type (full-time/part-time/contract) missing")
        else:
            filled_fields += 1

    completeness_score = (filled_fields / total_fields) if total_fields > 0 else 1.0

    # Only draft email if there are actual missing items
    email_draft = None
    if missing_items:
        candidate_name = candidate.name or "Candidate"
        missing_list_str = "\n".join(f"  • {item}" for item in missing_items)

        email_draft = f"""Subject: Request for Additional Information — Your Application

Dear {candidate_name},

Thank you for submitting your CV and for your interest. We are currently reviewing your application and have found that some details in your professional experience section are incomplete or unclear.

To ensure your profile is evaluated accurately and fairly, we kindly request that you provide the following information:

{missing_list_str}

Please reply to this email with the requested details at your earliest convenience. Providing complete information will help ensure your application receives full consideration.

If any of the gaps in your employment history are due to further studies, freelance work, personal responsibilities, or other activities, we encourage you to mention that as well — context is always helpful.

Thank you for your time and cooperation.

Best regards,  
TALASH HR Recruitment System"""

    return {
        "missing_fields": missing_items,
        "completeness_score": round(completeness_score, 2),
        "email_draft": email_draft
    }


# SECTION 7: MAIN PIPELINE — analyze_experience()

def analyze_experience(candidate_id: int) -> dict:
    """
    Master function. Called from app.py after a CV is uploaded.

    Steps:
      1. Load Experience and Education records from DB
      2. Run all 5 sub-analyzers
      3. Compute weighted final_score
      4. Return a single flat/nested dict (will be JSON-serialized by db_operations)

    The result dict is stored in AnalysisCache with module="experience_profile".
    """
    db = SessionLocal()

    try:
        candidate  = db.query(Candidate).filter(Candidate.id == candidate_id).first()
        educations = db.query(Education).filter(Education.candidate_id == candidate_id).all()
        experiences = db.query(Experience).filter(Experience.candidate_id == candidate_id).all()
    finally:
        db.close()

    if not experiences:
        return {
            "has_data": False,
            "message": "No experience records found for this candidate.",
            "final_score": 0.0
        }

    # --- Run all sub-analyzers ---
    exp_overlaps     = detect_exp_overlaps(experiences)
    edu_exp_overlaps = detect_edu_exp_overlaps(educations, experiences)
    gaps             = detect_professional_gaps(experiences, educations)
    progression      = analyze_career_progression(experiences)
    missing_info     = detect_missing_info(candidate, experiences)

    # Scoring

    # Continuity score: penalize unexplained gaps
    unexplained_gaps = [g for g in gaps if not g["justified"]]
    gap_penalty = min(len(unexplained_gaps) * 0.15, 0.6)
    continuity_score = round(1.0 - gap_penalty, 2)

    # Consistency score: penalize suspicious overlaps (high-suspicion ones)
    suspicious_overlaps = [o for o in exp_overlaps if o["suspicion"] == "high"]
    overlap_penalty = min(len(suspicious_overlaps) * 0.2, 0.6)
    consistency_score = round(1.0 - overlap_penalty, 2)

    # Progression score: directly from analyzer
    progression_score = progression["progression_score"]

    # Completeness score: directly from missing info analyzer
    completeness_score = missing_info["completeness_score"]

    # Weighted final score
    final_score = round(
        0.35 * continuity_score   +   # Gap-free continuity matters most
        0.30 * progression_score  +   # Career growth is highly valued
        0.20 * consistency_score  +   # No suspicious overlaps
        0.15 * completeness_score,    # Data quality
        2
    )

    # --- Interpretation ---
    if final_score >= 0.80:
        interpretation = "Excellent professional profile — consistent, progressive, and well-documented."
    elif final_score >= 0.65:
        interpretation = "Strong profile — minor gaps or inconsistencies, but overall positive trajectory."
    elif final_score >= 0.45:
        interpretation = "Moderate profile — some unexplained gaps or stagnation detected."
    else:
        interpretation = "Weak profile — significant gaps, overlaps, or missing information require clarification."

    return {
        "has_data": True,

        # Summary scores
        "final_score": final_score,
        "continuity_score": continuity_score,
        "progression_score": progression_score,
        "consistency_score": consistency_score,
        "completeness_score": completeness_score,
        "interpretation": interpretation,

        # Detailed findings
        "exp_overlaps": exp_overlaps,
        "edu_exp_overlaps": edu_exp_overlaps,
        "gaps": gaps,
        "progression": progression,
        "missing_info": missing_info,

        # Quick counters for UI metrics
        "total_roles": len(experiences),
        "unexplained_gaps_count": len(unexplained_gaps),
        "suspicious_overlaps_count": len(suspicious_overlaps),
        "trajectory": progression.get("trajectory", "unknown")
    }
