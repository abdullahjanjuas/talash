# journal_analyzer.py
# Module 3.2-i: Journal Publication Analysis
#
# PIPELINE:
#   1. Load all journal publications from DB for a candidate
#   2. Send to Llama (via Groq) to evaluate each journal on:
#      - WoS / Scopus indexing status
#      - Quartile ranking (Q1–Q4)
#      - Authorship role (first / corresponding / co-author)
#      - Impact factor estimate
#      - Overall quality interpretation
#   3. Compute per-paper scores and an aggregate journal_score
#   4. Return a flat/nested dict → stored in AnalysisCache under module='journal_profile'
#
# WHY GROQ+LLAMA instead of a static database?
#   Journal metadata (indexing, quartile) is dynamic and we don't carry a local
#   lookup table for 30 000+ journals.  Llama-3.1-70b-versatile has reasonable
#   pre-training knowledge about major venues.  We constrain it to return JSON
#   and explicitly tell it not to fabricate; the result is "best-effort" with
#   an explicit uncertainty field, which is honest for an academic demo system.

import json
from datetime import datetime
from groq import Groq
import os
from dotenv import load_dotenv
from database import SessionLocal
from models import Publication, AnalysisCache

load_dotenv()
client = Groq(api_key=os.getenv("GROQ_API_KEY"))
MODEL = "llama-3.3-70b-versatile"


# ---------------------------------------------------------------------------
# SECTION 1 — LLM CALL
# ---------------------------------------------------------------------------

def _llm_analyze_journals(papers: list) -> dict:
    """
    Ask Llama to evaluate each journal paper.
    Returns a structured dict or a safe fallback on failure.
    """
    papers_text = json.dumps(papers, indent=2)

    prompt = f"""You are an academic publication evaluator specializing in journal quality assessment.

Analyze the following journal papers and return ONLY a valid JSON object — no explanation, no markdown fences.

For each paper determine:
1. wos_indexed: true/false — is this journal indexed in Web of Science?
2. scopus_indexed: true/false — is this journal indexed in Scopus?
3. quartile: "Q1", "Q2", "Q3", "Q4", or "unknown"
4. impact_factor: numeric estimate or null if truly unknown
5. authorship_role: examine the authors list; assume first author = first in list, last author = corresponding/senior. Return "first_author", "corresponding_author", "first_and_corresponding", "co_author", or "unknown"
6. publisher: publisher name (e.g. "Elsevier", "IEEE", "Springer", "MDPI") or "unknown"
7. quality_note: one sentence plain-text interpretation of this paper's academic standing
8. confidence: "high", "medium", or "low" — how confident you are in this assessment

Return this exact JSON structure:
{{
  "papers": [
    {{
      "title": "...",
      "venue": "...",
      "year": "...",
      "wos_indexed": false,
      "scopus_indexed": false,
      "quartile": "unknown",
      "impact_factor": null,
      "authorship_role": "unknown",
      "publisher": "unknown",
      "quality_note": "...",
      "confidence": "medium"
    }}
  ],
  "summary": {{
    "total_journal_papers": 0,
    "wos_count": 0,
    "scopus_count": 0,
    "q1_count": 0,
    "q2_count": 0,
    "first_author_count": 0,
    "high_impact_count": 0,
    "top_venues": [],
    "overall_interpretation": "One paragraph plain-text assessment of the candidate's journal publication profile."
  }}
}}

Journal Papers to analyze:
{papers_text}
"""

    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": "You output only valid JSON. Never add markdown fences or extra text."},
                {"role": "user", "content": prompt}
            ],
            temperature=0,
            max_tokens=3000
        )
        raw = response.choices[0].message.content.strip()

        # Strip accidental markdown fences
        if raw.startswith("```"):
            parts = raw.split("```")
            raw = parts[1] if len(parts) > 1 else parts[0]
            if raw.startswith("json"):
                raw = raw[4:]
        raw = raw.strip()

        return json.loads(raw)

    except Exception as e:
        return {
            "papers": [],
            "summary": {
                "total_journal_papers": len(papers),
                "wos_count": 0,
                "scopus_count": 0,
                "q1_count": 0,
                "q2_count": 0,
                "first_author_count": 0,
                "high_impact_count": 0,
                "top_venues": [],
                "overall_interpretation": f"Analysis failed: {str(e)}"
            }
        }


# ---------------------------------------------------------------------------
# SECTION 2 — SCORING
# ---------------------------------------------------------------------------

def _compute_journal_score(summary: dict, papers: list) -> float:
    """
    Produce a 0–1 journal quality score based on indexing, quartiles,
    authorship, and impact factor presence.

    Weights (must sum to 1.0):
      40%  indexing quality  (WoS > Scopus > neither)
      30%  quartile spread   (Q1 >> Q2 > Q3 > Q4)
      20%  authorship role   (first/corresponding > co-author)
      10%  impact factor     (any non-null IF = good)
    """
    n = len(papers)
    if n == 0:
        return 0.0

    # Indexing score per paper
    wos_count    = summary.get("wos_count", 0)
    scopus_count = summary.get("scopus_count", 0)
    # a WoS paper also usually counts as Scopus — score separately
    indexing_score = (0.6 * wos_count + 0.4 * scopus_count) / n
    indexing_score = min(indexing_score, 1.0)

    # Quartile score
    q1 = summary.get("q1_count", 0)
    q2 = summary.get("q2_count", 0)
    q3 = sum(1 for p in papers if p.get("quartile") == "Q3")
    q4 = sum(1 for p in papers if p.get("quartile") == "Q4")
    quartile_score = (1.0 * q1 + 0.7 * q2 + 0.4 * q3 + 0.1 * q4) / n

    # Authorship score
    fa = summary.get("first_author_count", 0)
    fac = sum(1 for p in papers if p.get("authorship_role") in
              ["first_and_corresponding", "corresponding_author"])
    authorship_score = (1.0 * fac + 0.8 * fa) / n
    authorship_score = min(authorship_score, 1.0)

    # Impact factor presence
    hi = summary.get("high_impact_count", 0)
    if_score = min(hi / n, 1.0)

    final = (
        0.40 * indexing_score +
        0.30 * quartile_score +
        0.20 * authorship_score +
        0.10 * if_score
    )
    return round(final, 3)


# ---------------------------------------------------------------------------
# SECTION 3 — MAIN ENTRY POINT
# ---------------------------------------------------------------------------

def analyze_journal_papers(candidate_id: int) -> dict:
    """
    Main function called from app.py.
    Returns a dict stored in AnalysisCache under module='journal_profile'.
    """
    db = SessionLocal()
    try:
        pubs = db.query(Publication).filter(
            Publication.candidate_id == candidate_id,
            Publication.pub_type == "journal"
        ).all()
    finally:
        db.close()

    if not pubs:
        return {
            "has_data": False,
            "message": "No journal papers found for this candidate.",
            "journal_score": 0.0,
            "computed_at": datetime.now().isoformat()
        }

    # Build list for LLM
    papers_input = []
    for p in pubs:
        authors = json.loads(p.authors_json) if p.authors_json else []
        papers_input.append({
            "title": p.title,
            "venue": p.venue,
            "year": p.year,
            "authors": authors
        })

    analysis = _llm_analyze_journals(papers_input)

    # Ensure summary fields exist with safe defaults
    summary = analysis.get("summary", {})
    papers_out = analysis.get("papers", [])

    # Recount from per-paper data to be safe
    summary["wos_count"]         = sum(1 for p in papers_out if p.get("wos_indexed"))
    summary["scopus_count"]      = sum(1 for p in papers_out if p.get("scopus_indexed"))
    summary["q1_count"]          = sum(1 for p in papers_out if p.get("quartile") == "Q1")
    summary["q2_count"]          = sum(1 for p in papers_out if p.get("quartile") == "Q2")
    summary["first_author_count"]= sum(1 for p in papers_out if p.get("authorship_role")
                                       in ["first_author", "first_and_corresponding"])
    summary["high_impact_count"] = sum(1 for p in papers_out if p.get("impact_factor") is not None
                                       and isinstance(p.get("impact_factor"), (int, float))
                                       and p["impact_factor"] > 1.0)
    summary["total_journal_papers"] = len(papers_out)

    journal_score = _compute_journal_score(summary, papers_out)

    return {
        "has_data": True,
        "papers": papers_out,
        "summary": summary,
        "journal_score": journal_score,
        "computed_at": datetime.now().isoformat()
    }
