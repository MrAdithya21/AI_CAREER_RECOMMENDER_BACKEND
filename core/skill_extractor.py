import os
import google.generativeai as genai
from dotenv import load_dotenv
import time

load_dotenv()
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))

PRIMARY_MODEL = "gemini-1.5-pro"
FALLBACK_MODEL = "gemini-1.5-flash"

def parse_skill_list(text: str) -> list[str]:
    return sorted(set(
        skill.strip().lower()
        for skill in text.replace("\n", "").split(",")
        if skill.strip().isalpha() and len(skill.strip()) > 1
    ))

from core.skills_db import skills_db
from core.recommender import extract_skills_with_llm

def extract_skills_from_resume(text):
    llm_result = extract_skills_with_llm(text)
    
    # Step 1: Parse LLM comma-separated response
    llm_skills = [s.strip().lower() for s in llm_result.split(",") if s.strip()]

    # Step 2: Keyword match from known DB
    text_lower = text.lower()
    keyword_skills = [skill for skill in skills_db if skill in text_lower]

    # Step 3: Combine both
    final_skills = sorted(set(llm_skills + keyword_skills))
    return final_skills
