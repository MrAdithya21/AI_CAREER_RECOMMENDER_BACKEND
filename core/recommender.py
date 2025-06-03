import os
import re
import json
from datetime import datetime
from dateutil import parser
from pdfminer.high_level import extract_text
from dotenv import load_dotenv
import google.generativeai as genai
from sentence_transformers import util

from core.embedder import embed_skills

load_dotenv()
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))


def extract_sections(text: str):
    sections = {}
    current_section = "general"
    sections[current_section] = []

    for line in text.split("\n"):
        line_clean = line.strip().lower()

        if re.match(r"^(work\s+)?experience$|^professional experience$|^employment$", line_clean):
            current_section = "experience"
        elif re.match(r"^education$|^academic background$", line_clean):
            current_section = "education"
        elif re.match(r"^projects$|^personal projects$", line_clean):
            current_section = "projects"
        elif re.match(r"^certifications?$|^courses?$", line_clean):
            current_section = "certifications"
        elif re.match(r"^skills$", line_clean):
            current_section = "skills"

        if current_section not in sections:
            sections[current_section] = []
        sections[current_section].append(line)

    return sections


def extract_experience_from_text(text: str) -> int:
    sections = extract_sections(text)
    experience_text = "\n".join(sections.get("experience", []))

    date_range_pattern = r"([A-Z][a-z]+\s+\d{4})\s*[\u2013\u2014\-]\s*(Present|[A-Z][a-z]+\s+\d{4})"
    matches = re.findall(date_range_pattern, experience_text)

    total_months = 0
    for start, end in matches:
        try:
            start_date = parser.parse(start)
            end_date = datetime.now() if "present" in end.lower() else parser.parse(end)
            months = (end_date.year - start_date.year) * 12 + (end_date.month - start_date.month)
            if months > 0:
                total_months += months
                print(f"✅ COUNTED: {start} to {end} → {months} months")
        except Exception as e:
            print(f"❌ PARSE ERROR: {start} to {end} → {e}")

    years = round(total_months / 12)
    print(f"📊 FINAL Work Experience: {years} years")
    return years


def extract_resume_text(file_path):
    full_text = extract_text(file_path)
    experience = extract_experience_from_text(full_text)
    return {
        "text": full_text,
        "experience": experience
    }


def extract_skills_with_llm(resume_text):
    prompt = f"""
Extract all relevant technical and soft skills from the following resume text. This includes:

- Programming languages (Python, R, Java, etc.)
- Frameworks and libraries (Scikit-learn, React, Tableau, etc.)
- Data science/statistics terms (A/B Testing, Regression, Clustering, etc.)
- Tools and platforms (AWS, Azure, Git, Power BI, etc.)
- Soft skills (Teamwork, Communication, Agile, etc.)

Return as a comma-separated list of clean, lowercase skill names.

Resume:
{resume_text}
"""
    try:
        model = genai.GenerativeModel("gemini-1.5-pro")
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        if "quota" in str(e).lower() or "429" in str(e):
            print("⚠️ Gemini PRO quota hit. Falling back to Flash...")
            model = genai.GenerativeModel("gemini-1.5-flash")
            response = model.generate_content(prompt)
            return response.text.strip()
        raise e


def match_careers(user_skills):
    with open("data/career_paths.json") as f:
        careers = json.load(f)

    user_vec = embed_skills(user_skills)
    scored = []

    for career in careers:
        career_vec = embed_skills(career["required_skills"])
        score = util.cos_sim(user_vec, career_vec).item()
        scored.append((career, score))

    return sorted(scored, key=lambda x: x[1], reverse=True)[:3]
