"""
llm_extractor.py
=================
Uses Groq's Llama 3.1 8B model to convert raw CV text into structured JSON.
The LLM prompt defines a strict JSON schema and extraction rules to ensure
consistent output across different CV formats.

Pipeline:
  1. Receive full CV text from parser.py
  2. Truncate to 12K chars (LLM context window limit)
  3. Inject text into the EXTRACTION_PROMPT template
  4. Call Groq API with temperature=0 for deterministic output
  5. Strip markdown fences if present
  6. Parse JSON and fill missing keys with safe defaults
  7. Return success dict with parsed data, or error dict on failure
"""

from groq import Groq
import json
import os
from dotenv import load_dotenv

load_dotenv()

# Groq client — reads GROQ_API_KEY from .env
client = Groq(api_key=os.getenv("GROQ_API_KEY"))

# Fast/cheap model for extraction; 70B model reserved for analysis modules
MODEL_NAME = "openai/gpt-oss-20b"

# The system-level instruction template.
# <<<CV_TEXT>>> is replaced with the actual CV text at runtime.
# The schema defines every field the database expects so LLM output
# maps directly to models.py tables without post-processing.
EXTRACTION_PROMPT = """
You are a highly precise CV/Resume parser.

STRICT RULES:
- Return ONLY valid JSON.
- No explanations, no markdown, no extra text.
- Do NOT hallucinate.
- Use null for missing values.
- Use [] for empty lists.
- Keep all keys present.
- Extract ALL experience entries separately.
- If bullet points exist under experience, DO NOT merge them.
- Store ALL bullet points as a single string in the "description" field, joined by newlines (\n).
- NEVER summarize multiple bullet points into one sentence.

SCHEMA:
{
  "personal": {
    "name": "",
    "email": "",
    "phone": "",
    "address": ""
  },
  "education": [
    {
      "level": "",
      "degree": "",
      "institution": "",
      "cgpa": null,
      "percentage": null,
      "board": "",
      "specialization": "",
      "start_year": "",
      "end_year": ""
    }
  ],
  "experience": [
    {
      "title": "",
      "organization": "",
      "start_date": "",
      "end_date": "",
      "type": "",
      "description": ""
    }
  ],
  "publications": [
    {
      "type": "",
      "title": "",
      "venue": "",
      "year": "",
      "authors": []
    }
  ],
  "skills": [],
  "supervision": {
    "phd_count": 0,
    "ms_count": 0,
    "details": []
  },
  "patents": [
    {
      "number": "",
      "title": "",
      "year": ""
    }
  ],
  "books": [
    {
      "title": "",
      "publisher": "",
      "year": "",
      "role": ""
    }
  ],
  "projects": [
    {
      "title": "",
      "organization": "",
      "start_date": "",
      "end_date": "",
      "description": "",
      "technologies": "",
      "role": ""
    }
  ]
}

CV TEXT:
<<<CV_TEXT>>>
"""

def extract_cv_data(cv_text: str) -> dict:
    """
    Main entry point. Accepts raw CV text, returns structured JSON dict.

    Returns:
        On success: {"success": True, "data": <parsed dict>}
        On failure: {"success": False, "error": <msg>, "raw": <raw LLM output>}
    """
    # Truncate to 12K characters to fit within the model's context window
    MAX_CHARS = 12000
    if len(cv_text) > MAX_CHARS:
        cv_text = cv_text[:MAX_CHARS]

    # Inject CV text into the extraction prompt template
    prompt = EXTRACTION_PROMPT.replace("<<<CV_TEXT>>>", cv_text)

    try:
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": "You are a JSON-only output machine. You must return only raw valid JSON with no explanation, no markdown, no backticks, no preamble, no postamble. Just the JSON object."},
                {"role": "user", "content": prompt}
            ],
            temperature=0,
            max_tokens=4000,
            response_format={"type": "json_object"}
        )

        raw_response = response.choices[0].message.content.strip()

        if raw_response.startswith("```"):
            raw_response = raw_response.split("```")[1]

        raw_response = raw_response.strip()

        extracted = json.loads(raw_response)

        defaults = {
            "personal": {},
            "education": [],
            "experience": [],
            "publications": [],
            "skills": [],
            "supervision": {},
            "patents": [],
            "books": [],
            "projects": []
        }

        for key, default_value in defaults.items():
            if key not in extracted:
                extracted[key] = default_value

        return {"success": True, "data": extracted}

    except json.JSONDecodeError:
        return {
            "success": False,
            "error": "Invalid JSON from model",
            "raw": raw_response
        }

    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }

# ---------------------------------------------------------------------------
# Standalone test — run directly to verify the LLM extraction pipeline
# Usage:  python llm_extractor.py
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print("Testing Groq + Llama 3...")

    test_cv = """
    Ahmed Khan
    Email: ahmed@gmail.com
    Phone: 03001234567

    EDUCATION:
    BS Computer Science, NUST, 2018-2022, CGPA: 3.5

    EXPERIENCE:
    Data Analyst Intern, XYZ Company, 2022-2023

    SKILLS:
    Python, SQL, Machine Learning
    """

    result = extract_cv_data(test_cv)

    if result["success"]:
        print("\nSUCCESS")
        print(json.dumps(result["data"], indent=2))
    else:
        print("\nFAILED:", result["error"])
        print(result.get("raw", ""))
