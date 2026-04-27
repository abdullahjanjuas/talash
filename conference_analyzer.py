# conference_analyzer.py
# Initial/partial implementation — Conference Paper Analysis Module
# Covers: paper extraction, authorship role, basic venue quality interpretation

import json
from datetime import datetime
from database import SessionLocal
from models import Publication


def analyze_conference_papers(candidate_id: int) -> dict:
    """
    Analyzes conference publications for a candidate.
    Initial version covers:
    - Identifying conference papers from publications
    - Determining authorship role (first, corresponding, co-author)
    - Basic LLM-based venue quality interpretation
    Returns a dict that gets stored in AnalysisCache under module='conference_profile'
    """
    db = SessionLocal()
    try:
        pubs = db.query(Publication).filter(
            Publication.candidate_id == candidate_id,
            Publication.pub_type == "conference"
        ).all()

        if not pubs:
            return {
                "has_data": False,
                "message": "No conference papers found for this candidate.",
                "computed_at": datetime.now().isoformat()
            }

        # Build list of papers for LLM analysis
        papers = []
        for p in pubs:
            authors = json.loads(p.authors_json) if p.authors_json else []
            papers.append({
                "title": p.title,
                "venue": p.venue,
                "year": p.year,
                "authors": authors
            })

    finally:
        db.close()

    # Call LLM to analyze the conference papers
    analysis = _llm_analyze_conference_papers(papers)
    analysis["computed_at"] = datetime.now().isoformat()
    analysis["has_data"] = True
    return analysis


def _llm_analyze_conference_papers(papers: list) -> dict:
    """
    Sends conference paper list to LLM for assessment.
    Returns structured JSON with per-paper analysis and an overall summary.
    """
    import anthropic

    client = anthropic.Anthropic()

    papers_text = json.dumps(papers, indent=2)

    prompt = f"""You are an academic publication evaluator. Analyze the following conference papers and return a JSON object only — no explanation, no markdown.

Conference Papers:
{papers_text}

For each paper, determine:
1. authorship_role: Based on author order, classify as "first_author", "last_author", "co_author", or "unknown" (assume first in list = first author, last = corresponding/senior).
2. venue_tier: Based on your knowledge of the conference name, classify as "A*", "A", "B", "C", or "unknown".
3. venue_maturity: If you can tell from the conference name (e.g. "28th IEEE ..."), extract the edition number as integer or null.
4. indexing: List likely indexing from ["IEEE Xplore", "ACM DL", "Springer", "Scopus", "unknown"] based on the venue name.
5. quality_note: A one-sentence plain-text interpretation of this paper's academic standing.

Return this exact JSON structure:
{{
  "papers": [
    {{
      "title": "...",
      "venue": "...",
      "year": "...",
      "authorship_role": "...",
      "venue_tier": "...",
      "venue_maturity": null,
      "indexing": ["..."],
      "quality_note": "..."
    }}
  ],
  "summary": {{
    "total_conference_papers": 0,
    "a_star_count": 0,
    "first_author_count": 0,
    "top_venues": ["..."],
    "overall_interpretation": "One paragraph plain-text assessment of the candidate's conference publication profile."
  }}
}}
"""

    try:
        message = client.messages.create(
            model="claude-opus-4-5",
            max_tokens=2000,
            messages=[{"role": "user", "content": prompt}]
        )
        raw = message.content[0].text.strip()
        # Strip markdown fences if present
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        return json.loads(raw.strip())
    except Exception as e:
        return {
            "papers": [],
            "summary": {
                "total_conference_papers": len(papers),
                "a_star_count": 0,
                "first_author_count": 0,
                "top_venues": [],
                "overall_interpretation": f"Analysis failed: {str(e)}"
            }
        }