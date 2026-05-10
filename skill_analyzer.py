# skill_analyzer.py
# Module 3.9: Skill Alignment with Job Roles and Research Publications
#
# PIPELINE:
#   1. Load Skills, Experience, Publications, Projects from DB
#   2. Call Llama to cross-reference each claimed skill against:
#      - Job titles + descriptions  (experience evidence)
#      - Publication titles/venues  (research evidence)
#      - Project descriptions       (project evidence)
#   3. Classify each skill as: strongly_evidenced / partially_evidenced /
#      weakly_evidenced / unsupported
#   4. If a job description is provided, compute job_relevance_score
#   5. Return dict → AnalysisCache under module='skill_profile'

import json
from datetime import datetime
from groq import Groq
import os
from dotenv import load_dotenv
from database import SessionLocal
from models import Skill, Experience, Publication, Project

load_dotenv()
client = Groq(api_key=os.getenv("GROQ_API_KEY"))
MODEL = "llama-3.3-70b-versatile"


# ---------------------------------------------------------------------------
# SECTION 1 — LLM CALL
# ---------------------------------------------------------------------------

def _llm_analyze_skills(
    skills: list,
    experience_summary: str,
    publication_summary: str,
    project_summary: str,
    job_description: str = ""
) -> dict:
    """
    Ask Llama to evaluate each claimed skill against the candidate's evidence.
    """

    jd_section = (
        f"\nTarget Job Description:\n{job_description}\n"
        if job_description
        else "\nNo target job description provided.\n"
    )

    prompt = f"""You are a talent analyst evaluating whether a candidate's claimed skills are backed by real evidence from their CV.

Claimed Skills:
{json.dumps(skills)}

Experience Summary:
{experience_summary}

Publications Summary:
{publication_summary}

Projects Summary:
{project_summary}
{jd_section}

For each claimed skill, evaluate:
1. evidence_level: "strongly_evidenced" (appears in multiple sections),
   "partially_evidenced" (appears in one section), "weakly_evidenced" (implied but not explicit),
   or "unsupported" (no evidence found)
2. evidence_sources: list from ["experience", "publications", "projects", "education"] where evidence was found
3. evidence_note: one sentence explaining the basis for your assessment
4. job_relevance: "highly_relevant", "relevant", "somewhat_relevant", "not_relevant"
   (only if a job description was provided, else "not_assessed")

Then produce an overall summary.

Return ONLY this exact JSON — no markdown, no explanation:
{{
  "skill_assessments": [
    {{
      "skill": "...",
      "evidence_level": "partially_evidenced",
      "evidence_sources": [],
      "evidence_note": "...",
      "job_relevance": "not_assessed"
    }}
  ],
  "summary": {{
    "total_skills": 0,
    "strongly_evidenced_count": 0,
    "partially_evidenced_count": 0,
    "weakly_evidenced_count": 0,
    "unsupported_count": 0,
    "top_evidenced_skills": [],
    "unsupported_skills": [],
    "job_alignment_score": null,
    "overall_interpretation": "One paragraph summary of skill credibility and alignment."
  }}
}}
"""
    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": "You output only valid JSON. No markdown fences or extra text."},
                {"role": "user", "content": prompt}
            ],
            temperature=0,
            max_tokens=3000
        )
        raw = response.choices[0].message.content.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        return json.loads(raw.strip())

    except Exception as e:
        return {
            "skill_assessments": [
                {"skill": s, "evidence_level": "unknown", "evidence_sources": [],
                 "evidence_note": "Analysis failed.", "job_relevance": "not_assessed"}
                for s in skills
            ],
            "summary": {
                "total_skills": len(skills),
                "strongly_evidenced_count": 0,
                "partially_evidenced_count": 0,
                "weakly_evidenced_count": 0,
                "unsupported_count": 0,
                "top_evidenced_skills": [],
                "unsupported_skills": skills,
                "job_alignment_score": None,
                "overall_interpretation": f"Analysis failed: {str(e)}"
            }
        }


# ---------------------------------------------------------------------------
# SECTION 2 — DATA HELPERS
# ---------------------------------------------------------------------------

def _build_experience_summary(experiences) -> str:
    parts = []
    for e in experiences:
        line = f"- {e.title or 'Unknown role'} at {e.organization or 'Unknown org'}"
        if e.description:
            line += f": {e.description[:200]}"
        parts.append(line)
    return "\n".join(parts) if parts else "No experience records."


def _build_publication_summary(publications) -> str:
    parts = []
    for p in publications:
        parts.append(f"- \"{p.title}\" in {p.venue or 'unknown venue'} ({p.year or '?'})")
    return "\n".join(parts) if parts else "No publications."


def _build_project_summary(projects) -> str:
    parts = []
    for pr in projects:
        line = f"- {pr.title or 'Unnamed project'}"
        if pr.technologies:
            line += f" [Tech: {pr.technologies}]"
        if pr.description:
            line += f": {pr.description[:150]}"
        parts.append(line)
    return "\n".join(parts) if parts else "No projects."


# ---------------------------------------------------------------------------
# SECTION 3 — SCORING
# ---------------------------------------------------------------------------

def _compute_skill_score(summary: dict) -> float:
    """
    0–1 credibility score for claimed skills.

    Weights:
      Strongly evidenced:   1.0 each
      Partially evidenced:  0.6 each
      Weakly evidenced:     0.2 each
      Unsupported:          0.0 each
    Normalized by total skills count.
    """
    total = summary.get("total_skills", 0)
    if total == 0:
        return 0.0

    score = (
        1.0 * summary.get("strongly_evidenced_count", 0) +
        0.6 * summary.get("partially_evidenced_count", 0) +
        0.2 * summary.get("weakly_evidenced_count", 0)
    ) / total

    return round(min(score, 1.0), 3)


# ---------------------------------------------------------------------------
# SECTION 4 — MAIN ENTRY POINT
# ---------------------------------------------------------------------------

def analyze_skills(candidate_id: int, job_description: str = "") -> dict:
    """
    Main function called from app.py.
    job_description: optional free-text job posting for relevance analysis.
    Stored in AnalysisCache under module='skill_profile'.
    """
    db = SessionLocal()
    try:
        skills_rows = db.query(Skill).filter(Skill.candidate_id == candidate_id).all()
        exp_rows    = db.query(Experience).filter(Experience.candidate_id == candidate_id).all()
        pub_rows    = db.query(Publication).filter(Publication.candidate_id == candidate_id).all()
        proj_rows   = db.query(Project).filter(Project.candidate_id == candidate_id).all()
    finally:
        db.close()

    if not skills_rows:
        return {
            "has_data": False,
            "message": "No skills found for this candidate.",
            "skill_score": 0.0,
            "computed_at": datetime.now().isoformat()
        }

    skills_list        = [s.skill_name for s in skills_rows if s.skill_name]
    experience_summary = _build_experience_summary(exp_rows)
    publication_summary= _build_publication_summary(pub_rows)
    project_summary    = _build_project_summary(proj_rows)

    result = _llm_analyze_skills(
        skills_list,
        experience_summary,
        publication_summary,
        project_summary,
        job_description
    )

    assessments = result.get("skill_assessments", [])
    summary     = result.get("summary", {})

    # Recount from per-skill data
    summary["total_skills"]                = len(assessments)
    summary["strongly_evidenced_count"]    = sum(1 for s in assessments if s.get("evidence_level") == "strongly_evidenced")
    summary["partially_evidenced_count"]   = sum(1 for s in assessments if s.get("evidence_level") == "partially_evidenced")
    summary["weakly_evidenced_count"]      = sum(1 for s in assessments if s.get("evidence_level") == "weakly_evidenced")
    summary["unsupported_count"]           = sum(1 for s in assessments if s.get("evidence_level") == "unsupported")
    summary["top_evidenced_skills"]        = [s["skill"] for s in assessments if s.get("evidence_level") == "strongly_evidenced"][:5]
    summary["unsupported_skills"]          = [s["skill"] for s in assessments if s.get("evidence_level") == "unsupported"]

    skill_score = _compute_skill_score(summary)

    return {
        "has_data": True,
        "skill_assessments": assessments,
        "summary": summary,
        "skill_score": skill_score,
        "job_description_provided": bool(job_description),
        "computed_at": datetime.now().isoformat()
    }
