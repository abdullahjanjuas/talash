# topic_coauthor_analyzer.py
# Module 3.6 + 3.7: Topic Variability & Co-Author Analysis
#
# PIPELINE:
#   1. Load all publications (journal + conference) from DB for a candidate
#   2. Call Llama to:
#      a. Cluster publications into research themes (topic variability)
#      b. Analyze co-authorship patterns (collaboration network)
#   3. Compute a diversity_score and collaboration_score
#   4. Return combined dict → AnalysisCache under module='topic_coauthor_profile'
#
# WHY ONE MODULE for both?
#   Both analyses run on the same publication data, so one LLM call covers both,
#   halving the API usage and keeping the cache entry coherent.

import json
from datetime import datetime
from groq import Groq
import os
from collections import Counter
from dotenv import load_dotenv
from database import SessionLocal
from models import Publication

load_dotenv()
client = Groq(api_key=os.getenv("GROQ_API_KEY"))
MODEL = "llama-3.3-70b-versatile"


# ---------------------------------------------------------------------------
# SECTION 1 — LLM CALL
# ---------------------------------------------------------------------------

def _llm_analyze_topics_and_coauthors(papers: list) -> dict:
    """
    Single LLM call that covers both topic variability and co-author patterns.
    """
    papers_text = json.dumps(papers, indent=2)

    prompt = f"""You are an academic research analyst. Analyze the following publications and return ONLY a valid JSON object — no markdown fences, no explanation.

TASK A — Topic Variability:
Group these papers into research themes (e.g. "Machine Learning", "Computer Vision", "NLP", "Cybersecurity", "Networks", "Software Engineering", "Data Science", "Human-Computer Interaction", etc.)
For each theme list which paper titles belong to it.

TASK B — Co-Author Analysis:
Extract all unique co-authors across all papers and identify:
- Which co-authors appear more than once (recurring collaborators)
- Average team size per paper
- Whether collaboration is broad (many unique co-authors) or tight (same group repeating)

Return this exact JSON structure:
{{
  "topic_analysis": {{
    "themes": [
      {{
        "theme": "Machine Learning",
        "paper_count": 0,
        "papers": ["paper title 1", "paper title 2"],
        "percentage": 0.0
      }}
    ],
    "dominant_topic": "...",
    "diversity_score": 0.0,
    "diversity_label": "Specialist",
    "topic_trend": "Stable",
    "interpretation": "One paragraph about the candidate's research focus."
  }},
  "coauthor_analysis": {{
    "total_unique_coauthors": 0,
    "recurring_collaborators": [
      {{"name": "...", "paper_count": 0}}
    ],
    "avg_team_size": 0.0,
    "collaboration_breadth": "Broad",
    "collaboration_style": "Team-oriented",
    "interpretation": "One paragraph about the candidate's collaboration patterns."
  }}
}}

SCORING GUIDE for diversity_score (0.0 to 1.0):
- 0.0–0.3: Specialist — almost all papers in one theme
- 0.3–0.6: Focused — 2-3 related themes
- 0.6–0.8: Interdisciplinary — 4+ themes with clear connections
- 0.8–1.0: Broad — many unrelated themes

SCORING for diversity_label: "Specialist", "Focused", "Interdisciplinary", or "Broad"

Publications to analyze:
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
        if raw.startswith("```"):
            parts = raw.split("```")
            raw = parts[1] if len(parts) > 1 else parts[0]
            if raw.startswith("json"):
                raw = raw[4:]
        return json.loads(raw.strip())

    except Exception as e:
        return {
            "topic_analysis": {
                "themes": [],
                "dominant_topic": "Unknown",
                "diversity_score": 0.0,
                "diversity_label": "Unknown",
                "topic_trend": "Unknown",
                "interpretation": f"Analysis failed: {str(e)}"
            },
            "coauthor_analysis": {
                "total_unique_coauthors": 0,
                "recurring_collaborators": [],
                "avg_team_size": 0.0,
                "collaboration_breadth": "Unknown",
                "collaboration_style": "Unknown",
                "interpretation": f"Analysis failed: {str(e)}"
            }
        }


# ---------------------------------------------------------------------------
# SECTION 2 — LOCAL COAUTHOR STATS (no LLM needed for raw counts)
# ---------------------------------------------------------------------------

def _compute_local_coauthor_stats(papers: list) -> dict:
    """
    Compute co-author statistics directly from the author lists.
    This is deterministic and doesn't need an LLM.
    """
    all_authors = []
    team_sizes  = []

    for p in papers:
        authors = p.get("authors", [])
        # Remove the candidate themselves (assume they appear most frequently)
        team_sizes.append(len(authors))
        all_authors.extend(authors)

    if not all_authors:
        return {
            "total_unique_coauthors": 0,
            "most_frequent": [],
            "avg_team_size": 0.0
        }

    counter = Counter(all_authors)
    # most_frequent: top 5 recurring authors
    most_frequent = [
        {"name": name, "paper_count": count}
        for name, count in counter.most_common(5)
        if count > 1
    ]

    return {
        "total_unique_coauthors": len(counter),
        "most_frequent": most_frequent,
        "avg_team_size": round(sum(team_sizes) / len(team_sizes), 1) if team_sizes else 0.0
    }


# ---------------------------------------------------------------------------
# SECTION 3 — SCORING
# ---------------------------------------------------------------------------

def _compute_diversity_score(topic_analysis: dict) -> float:
    """Use the LLM-assigned diversity_score (already 0–1), clamped."""
    score = topic_analysis.get("diversity_score", 0.0)
    return round(max(0.0, min(1.0, float(score))), 3)


def _compute_collaboration_score(local_stats: dict, llm_analysis: dict) -> float:
    """
    0–1 score for collaboration richness.

    Weights:
      40%  breadth (total unique co-authors, normalized: 10+ = 1.0)
      35%  recurring collaborators (stable research group = good)
      25%  average team size (2–5 is healthy)
    """
    total_unique = local_stats.get("total_unique_coauthors", 0)
    breadth_score = min(total_unique / 10.0, 1.0)

    recurring = len(local_stats.get("most_frequent", []))
    recurrence_score = min(recurring / 3.0, 1.0)

    avg_size = local_stats.get("avg_team_size", 1.0)
    # Healthy team: 2–6 authors → score 1.0; solo or very large = lower
    if avg_size <= 1:
        size_score = 0.1
    elif avg_size <= 6:
        size_score = 0.8 + 0.2 * ((avg_size - 2) / 4)
    else:
        size_score = max(0.4, 1.0 - 0.05 * (avg_size - 6))

    final = (
        0.40 * breadth_score +
        0.35 * recurrence_score +
        0.25 * size_score
    )
    return round(final, 3)


# ---------------------------------------------------------------------------
# SECTION 4 — MAIN ENTRY POINT
# ---------------------------------------------------------------------------

def analyze_topics_and_coauthors(candidate_id: int) -> dict:
    """
    Main function called from app.py.
    Stored in AnalysisCache under module='topic_coauthor_profile'.
    """
    db = SessionLocal()
    try:
        pubs = db.query(Publication).filter(
            Publication.candidate_id == candidate_id
        ).all()
    finally:
        db.close()

    if not pubs:
        return {
            "has_data": False,
            "message": "No publications found for topic/co-author analysis.",
            "diversity_score": 0.0,
            "collaboration_score": 0.0,
            "computed_at": datetime.now().isoformat()
        }

    papers = []
    for p in pubs:
        authors = json.loads(p.authors_json) if p.authors_json else []
        papers.append({
            "title": p.title,
            "venue": p.venue,
            "year": p.year,
            "type": p.pub_type,
            "authors": authors
        })

    llm_result   = _llm_analyze_topics_and_coauthors(papers)
    local_stats  = _compute_local_coauthor_stats(papers)

    topic_analysis   = llm_result.get("topic_analysis", {})
    coauthor_llm     = llm_result.get("coauthor_analysis", {})

    diversity_score      = _compute_diversity_score(topic_analysis)
    collaboration_score  = _compute_collaboration_score(local_stats, coauthor_llm)

    # Merge local counts into coauthor section for richer display
    coauthor_llm["total_unique_coauthors"] = local_stats["total_unique_coauthors"]
    coauthor_llm["avg_team_size"]          = local_stats["avg_team_size"]
    coauthor_llm["most_frequent_local"]    = local_stats["most_frequent"]

    return {
        "has_data": True,
        "total_papers_analyzed": len(papers),
        "topic_analysis": topic_analysis,
        "coauthor_analysis": coauthor_llm,
        "diversity_score": diversity_score,
        "collaboration_score": collaboration_score,
        "computed_at": datetime.now().isoformat()
    }
