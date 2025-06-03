import os
import json
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))

def generate_career_paths(user_skills: list[str], experience: int = 0, model_name="gemini-1.5-flash"):
    prompt = f"""
You are an expert AI career advisor.

Based on the following skills:
{', '.join(user_skills)}

And estimated experience: {experience} years

Recommend 3 suitable career paths in valid JSON format.
Tailor suggestions to the candidate's experience level (e.g., junior-level roles if experience < 2 years).

Each career must include:
- "career": (string)
- "required_skills": (list of strings)
- "courses": (list of objects with "title" and "link")

Respond with only raw JSON. No explanation or markdown.

Example:
[
  {{
    "career": "Data Scientist",
    "required_skills": ["Python", "SQL", "Machine Learning"],
    "courses": [
      {{
        "title": "Data Science Specialization (Coursera)",
        "link": "https://www.coursera.org/specializations/jhu-data-science"
      }},
      {{
        "title": "Machine Learning by Andrew Ng",
        "link": "https://www.coursera.org/learn/machine-learning"
      }}
    ]
  }}
]
"""
    try:
        model = genai.GenerativeModel(model_name)
        response = model.generate_content(prompt)
        raw_text = response.text.strip()

        if "```json" in raw_text:
            raw_text = raw_text.split("```json")[1].split("```")[0].strip()
        elif "```" in raw_text:
            raw_text = raw_text.split("```")[1].strip()

        return json.loads(raw_text)

    except json.JSONDecodeError as e:
        raise ValueError(f"❌ Gemini returned invalid JSON:\n{raw_text}\n\nError: {e}")

    except Exception as e:
        raise RuntimeError(f"❌ Error during Gemini content generation: {e}")
