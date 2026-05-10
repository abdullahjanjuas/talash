# conference_analyzer.py
# Module 3.2-ii: Conference Paper Analysis
#
# PIPELINE:
#   1. Load all conference publications for a candidate from DB
#   2. Send to Llama (Groq) to evaluate each paper:
#      - A* ranking status
#      - Conference maturity (edition number)
#      - Proceedings indexing (IEEE / ACM / Springer / Scopus)
#      - Authorship role
#      - Overall quality interpretation
#   3. Compute a conference_score (0–1)
#   4. Return dict → stored in AnalysisCache under module='conference_profile'
#
# NOTE: Uses GROQ_API_KEY + llama-3.3-70b-versatile only.
#       No external API calls to CORE portal — Llama's training knowledge is used
#       with explicit confidence tagging so the system is honest about uncertainty.

import json
from datetime import datetime
from groq import Groq
import os
from dotenv import load_dotenv
from database import SessionLocal
from models import Publication

load_dotenv()
client = Groq(api_key=os.getenv("GROQ_API_KEY"))
MODEL = "llama-3.3-70b-versatile"


# ---------------------------------------------------------------------------
# SECTION 1 — LLM CALL
# ---------------------------------------------------------------------------

def _llm_analyze_conference_papers(papers: list) -> dict:
    """
    Send conference papers to Llama for structured quality assessment.
    Returns parsed JSON or a safe fallback dict.
    """
    papers_text = json.dumps(papers, indent=2)

    prompt = f"""You are an academic publication evaluator specializing in computer science conference quality assessment.

Analyze the following conference papers and return ONLY a valid JSON object — no markdown fences, no explanation.

For each paper determine:
1. authorship_role: examine the authors list; first in list = first author, last = corresponding/senior.
   Return "first_author", "corresponding_author", "first_and_corresponding", "co_author", or "unknown"
2. venue_tier: Based on the conference name, rank as "A*", "A", "B", "C", or "unknown"
   (A* = ICML, NeurIPS, CVPR, ICCV, ACL, EMNLP, SIGCOMM, OSDI, SOSP, WWW, VLDB, etc.)
3. venue_maturity: If the conference name mentions an edition (e.g. "28th IEEE"), extract the integer edition number, else null
4. indexing: list from ["IEEE Xplore", "ACM Digital Library", "Springer", "Scopus", "unknown"]
5. quality_note: one sentence plain-text interpretation of this paper's academic standing
6. confidence: "high", "medium", or "low"

Return this exact JSON structure:
{{
  "papers": [
    {{
      "title": "...",
      "venue": "...",
      "year": "...",
      "authorship_role": "unknown",
      "venue_tier": "unknown",
      "venue_maturity": null,
      "indexing": [],
      "quality_note": "...",
      "confidence": "medium"
    }}
  ],
  "summary": {{
    "total_conference_papers": 0,
    "a_star_count": 0,
    "a_rank_count": 0,
    "first_author_count": 0,
    "ieee_count": 0,
    "acm_count": 0,
    "top_venues": [],
    "overall_interpretation": "One paragraph plain-text assessment of the candidate's conference publication profile."
  }}
}}

Conference Papers to analyze:
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
                "total_conference_papers": len(papers),
                "a_star_count": 0,
                "a_rank_count": 0,
                "first_author_count": 0,
                "ieee_count": 0,
                "acm_count": 0,
                "top_venues": [],
                "overall_interpretation": f"Analysis failed: {str(e)}"
            }
        }


# ---------------------------------------------------------------------------
# SECTION 2 — SCORING
# ---------------------------------------------------------------------------

def _compute_conference_score(summary: dict, papers: list) -> float:
    """
    0–1 score for conference publication quality.

    Weights:
      45%  venue tier   (A* = 1.0, A = 0.75, B = 0.5, C = 0.25, unknown = 0.1)
      30%  authorship   (first/corresponding > co-author)
      15%  indexing     (IEEE/ACM indexed papers)
      10%  maturity     (venues with known edition numbers = established)
    """
    n = len(papers)
    if n == 0:
        return 0.0

    tier_map = {"A*": 1.0, "A": 0.75, "B": 0.5, "C": 0.25, "unknown": 0.1}
    tier_score = sum(tier_map.get(p.get("venue_tier", "unknown"), 0.1) for p in papers) / n

    fa_count = summary.get("first_author_count", 0)
    corr_count = sum(1 for p in papers if p.get("authorship_role") in
                     ["first_and_corresponding", "corresponding_author"])
    authorship_score = min((1.0 * corr_count + 0.8 * fa_count) / n, 1.0)

    indexed = sum(1 for p in papers
                  if any(idx in ["IEEE Xplore", "ACM Digital Library"]
                         for idx in p.get("indexing", [])))
    indexing_score = indexed / n

    mature = sum(1 for p in papers if p.get("venue_maturity") is not None)
    maturity_score = mature / n

    final = (
        0.45 * tier_score +
        0.30 * authorship_score +
        0.15 * indexing_score +
        0.10 * maturity_score
    )
    return round(final, 3)


# ---------------------------------------------------------------------------
# SECTION 3 — MAIN ENTRY POINT
# ---------------------------------------------------------------------------

def analyze_conference_papers(candidate_id: int) -> dict:
    """
    Main function called from app.py.
    Returns a dict stored in AnalysisCache under module='conference_profile'.
    """
    db = SessionLocal()
    try:
        pubs = db.query(Publication).filter(
            Publication.candidate_id == candidate_id,
            Publication.pub_type == "conference"
        ).all()
    finally:
        db.close()

    if not pubs:
        return {
            "has_data": False,
            "message": "No conference papers found for this candidate.",
            "conference_score": 0.0,
            "computed_at": datetime.now().isoformat()
        }

    papers_input = []
    for p in pubs:
        authors = json.loads(p.authors_json) if p.authors_json else []
        papers_input.append({
            "title": p.title,
            "venue": p.venue,
            "year": p.year,
            "authors": authors
        })

    analysis = _llm_analyze_conference_papers(papers_input)

    papers_out = analysis.get("papers", [])
    summary    = analysis.get("summary", {})

    # Recount from per-paper data to be reliable
    summary["total_conference_papers"] = len(papers_out)
    summary["a_star_count"]     = sum(1 for p in papers_out if p.get("venue_tier") == "A*")
    summary["a_rank_count"]     = sum(1 for p in papers_out if p.get("venue_tier") == "A")
    summary["first_author_count"] = sum(1 for p in papers_out if p.get("authorship_role")
                                        in ["first_author", "first_and_corresponding"])
    summary["ieee_count"] = sum(1 for p in papers_out
                                if "IEEE Xplore" in p.get("indexing", []))
    summary["acm_count"]  = sum(1 for p in papers_out
                                if "ACM Digital Library" in p.get("indexing", []))

    conference_score = _compute_conference_score(summary, papers_out)

    return {
        "has_data": True,
        "papers": papers_out,
        "summary": summary,
        "conference_score": conference_score,
        "computed_at": datetime.now().isoformat()
    }
