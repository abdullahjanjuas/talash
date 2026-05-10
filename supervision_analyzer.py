# supervision_analyzer.py
# Module 3.3 + 3.4 + 3.5: Student Supervision, Books, and Patents Analysis
#
# PIPELINE:
#   1. Load supervision data from LLM extraction (stored in Candidate/Publications)
#   2. Load books and patents from DB
#   3. Score supervision depth, book authorship quality, patent output
#   4. Use Llama to evaluate book publisher credibility and patent significance
#   5. Return combined dict → AnalysisCache under module='supervision_books_patents'
#
# DATA SOURCES:
#   - Supervision: extracted from CV text by llm_extractor.py and stored
#     in a "supervision" key.  We retrieve it from the raw AnalysisCache or
#     re-query from the extraction.  Since models.py doesn't have a Supervision
#     table, we pull from the raw LLM extraction stored in the JSON cache OR
#     fall back to counting publications co-authored with likely students.
#   - Books:  models.Book table
#   - Patents: models.Patent table

import json
from datetime import datetime
from groq import Groq
import os
from dotenv import load_dotenv
from database import SessionLocal
from models import Book, Patent, Publication, AnalysisCache

load_dotenv()
client = Groq(api_key=os.getenv("GROQ_API_KEY"))
MODEL = "llama-3.3-70b-versatile"


# ---------------------------------------------------------------------------
# SECTION 1 — BOOK ANALYSIS VIA LLM
# ---------------------------------------------------------------------------

def _llm_analyze_books(books_data: list) -> dict:
    """
    Ask Llama to assess publisher credibility and authorship role for each book.
    """
    if not books_data:
        return {"books_analyzed": [], "overall_book_note": "No books found."}

    prompt = f"""You are an academic publication evaluator. Analyze the following books and return ONLY valid JSON — no markdown, no explanation.

For each book determine:
1. publisher_tier: "Top-tier" (e.g. Springer, Elsevier, Wiley, MIT Press, CRC, IEEE Press, Oxford, Cambridge),
   "Mid-tier" (reputable academic presses), "Self-published/Unknown", or "unknown"
2. authorship_value: "sole_author", "lead_author", "co_author", "editor", or "unknown"
   (use the role field if available)
3. scholarly_value: "High", "Moderate", "Low", or "unknown"
4. note: one sentence interpretation

Return:
{{
  "books_analyzed": [
    {{
      "title": "...",
      "publisher": "...",
      "year": "...",
      "role": "...",
      "publisher_tier": "unknown",
      "authorship_value": "unknown",
      "scholarly_value": "unknown",
      "note": "..."
    }}
  ],
  "overall_book_note": "One sentence summary of the candidate's book authorship profile."
}}

Books:
{json.dumps(books_data, indent=2)}
"""
    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": "You output only valid JSON."},
                {"role": "user", "content": prompt}
            ],
            temperature=0,
            max_tokens=1500
        )
        raw = response.choices[0].message.content.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        return json.loads(raw.strip())
    except Exception as e:
        return {
            "books_analyzed": books_data,
            "overall_book_note": f"Analysis failed: {str(e)}"
        }


# ---------------------------------------------------------------------------
# SECTION 2 — SUPERVISION DATA EXTRACTION
# ---------------------------------------------------------------------------

def _get_supervision_data(candidate_id: int) -> dict:
    """
    Try to retrieve supervision data from the raw extraction cache.
    The LLM extractor stores supervision counts in the 'supervision' key.
    We look for it in a special 'raw_extraction' cache entry, falling back
    to zeros if not available (supervision info is rarely in CVs without
    explicit sections).
    """
    db = SessionLocal()
    try:
        # Check if raw extraction was cached
        raw_cache = db.query(AnalysisCache).filter(
            AnalysisCache.candidate_id == candidate_id,
            AnalysisCache.module == "raw_extraction"
        ).first()

        if raw_cache:
            data = json.loads(raw_cache.result_json)
            supervision = data.get("supervision", {})
            return {
                "phd_main": supervision.get("phd_count", 0),
                "ms_main": supervision.get("ms_count", 0),
                "phd_co": 0,   # usually not distinguished in CV
                "ms_co": 0,
                "details": supervision.get("details", []),
                "source": "extracted"
            }
    except Exception:
        pass
    finally:
        db.close()

    return {
        "phd_main": 0,
        "ms_main": 0,
        "phd_co": 0,
        "ms_co": 0,
        "details": [],
        "source": "not_found"
    }


# ---------------------------------------------------------------------------
# SECTION 3 — SCORING
# ---------------------------------------------------------------------------

def _compute_supervision_score(sup: dict) -> float:
    """
    0–1 score based on total students supervised.
    PhD weights 2×, MS weights 1×.
    Normalized: 10+ equivalent students → 1.0
    """
    equiv = 2 * (sup["phd_main"] + sup["phd_co"]) + (sup["ms_main"] + sup["ms_co"])
    return round(min(equiv / 10.0, 1.0), 3)


def _compute_book_score(books_analyzed: list) -> float:
    """
    0–1 based on publisher tier and authorship value.
    """
    if not books_analyzed:
        return 0.0

    tier_map  = {"Top-tier": 1.0, "Mid-tier": 0.6, "Self-published/Unknown": 0.2, "unknown": 0.1}
    role_map  = {"sole_author": 1.0, "lead_author": 0.85, "co_author": 0.6, "editor": 0.5, "unknown": 0.3}

    scores = []
    for b in books_analyzed:
        t = tier_map.get(b.get("publisher_tier", "unknown"), 0.1)
        r = role_map.get(b.get("authorship_value", "unknown"), 0.3)
        scores.append(0.6 * t + 0.4 * r)

    return round(sum(scores) / len(scores), 3)


def _compute_patent_score(patents: list) -> float:
    """
    0–1 based on number of patents (3+ → max score).
    """
    return round(min(len(patents) / 3.0, 1.0), 3)


# ---------------------------------------------------------------------------
# SECTION 4 — MAIN ENTRY POINT
# ---------------------------------------------------------------------------

def analyze_supervision_books_patents(candidate_id: int) -> dict:
    """
    Main function called from app.py.
    Stored in AnalysisCache under module='supervision_books_patents'.
    """
    db = SessionLocal()
    try:
        books_rows   = db.query(Book).filter(Book.candidate_id == candidate_id).all()
        patents_rows = db.query(Patent).filter(Patent.candidate_id == candidate_id).all()
    finally:
        db.close()

    # --- Supervision ---
    supervision = _get_supervision_data(candidate_id)
    supervision_score = _compute_supervision_score(supervision)

    # --- Books ---
    books_input = [
        {"title": b.title, "publisher": b.publisher, "year": b.year, "role": b.role}
        for b in books_rows
    ]
    book_analysis = _llm_analyze_books(books_input)
    books_analyzed = book_analysis.get("books_analyzed", [])
    book_score = _compute_book_score(books_analyzed)

    # --- Patents ---
    patents_list = [
        {"number": p.number, "title": p.title, "year": p.year}
        for p in patents_rows
    ]
    patent_score = _compute_patent_score(patents_list)

    # Combined weighted score
    # Supervision is most important for academic profiles
    combined_score = round(
        0.45 * supervision_score +
        0.30 * book_score +
        0.25 * patent_score,
        3
    )

    # Interpretation
    if combined_score >= 0.70:
        interpretation = "Strong scholarly output — notable supervision record, books, or patents."
    elif combined_score >= 0.40:
        interpretation = "Moderate scholarly contributions — some evidence of supervision or publishing."
    elif combined_score > 0.0:
        interpretation = "Limited scholarly output — minimal supervision, books, or patents on record."
    else:
        interpretation = "No supervision, book, or patent records found in this CV."

    return {
        "has_data": True,
        "supervision": supervision,
        "supervision_score": supervision_score,
        "books": books_analyzed,
        "book_overall_note": book_analysis.get("overall_book_note", ""),
        "book_score": book_score,
        "patents": patents_list,
        "patent_score": patent_score,
        "combined_score": combined_score,
        "interpretation": interpretation,
        "computed_at": datetime.now().isoformat()
    }
