# LLM Used to convert raw text into JSON 
# llama used from Groq API

from groq import Groq
import json
import os
from dotenv import load_dotenv

load_dotenv()

# Client Setup
client = Groq(api_key=os.getenv("GROQ_API_KEY"))

MODEL_NAME = "llama-3.1-8b-instant"

# PROMPT 
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

# MAIN FUNCTION
def extract_cv_data(cv_text: str) -> dict:

    MAX_CHARS = 12000
    if len(cv_text) > MAX_CHARS:
        cv_text = cv_text[:MAX_CHARS]

    prompt = EXTRACTION_PROMPT.replace("<<<CV_TEXT>>>", cv_text)

    try:
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": "You output only valid JSON."},
                {"role": "user", "content": prompt}
            ],
            temperature=0,
            max_tokens=3000
        )

        raw_response = response.choices[0].message.content.strip()

        # CLEAN RESPONSE
        if raw_response.startswith("```"):
            raw_response = raw_response.split("```")[1]

        raw_response = raw_response.strip()

        # PARSE JSON
        extracted = json.loads(raw_response)

        # ENSURE KEYS
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


# TEST
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