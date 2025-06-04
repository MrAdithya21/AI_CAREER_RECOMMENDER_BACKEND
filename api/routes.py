import os
import re
import json
import tempfile
import dateutil.parser
from datetime import datetime
from dotenv import load_dotenv
from fastapi import APIRouter, File, UploadFile, Form, Query, Request, Body
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import google.generativeai as genai

from core.recommender import extract_resume_text, extract_skills_with_llm, match_careers
from core.skill_extractor import extract_skills_from_resume
from core.career_matcher import generate_career_paths
from core.salary_fetcher import fetch_salary_samples

load_dotenv()
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))

router = APIRouter()

@router.get("/")
async def root():
    return {"message": "AI Career Recommender API is running!"}


@router.post("/upload-resume")
async def upload_resume(file: UploadFile = File(...)):
    tmp_path = ""
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            tmp.write(await file.read())
            tmp_path = tmp.name

        resume_data = extract_resume_text(tmp_path)
        resume_text = resume_data.get("text", "")
        experience = resume_data.get("experience", 0)

        skills = extract_skills_with_llm(resume_text)
        skills_list = [s.strip().lower() for s in skills.split(",") if s.strip()]

        top_matches = match_careers(skills_list)
        matched_careers = [
            {
                "title": career.get("title", "Untitled Role"),
                "description": career.get("description", "No description provided."),
                "score": round(score, 3)
            }
            for career, score in top_matches
        ]

        return JSONResponse(content={
            "text": resume_text,
            "experience": experience,
            "skills": skills_list,
            "careers": matched_careers
        })

    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)


@router.post("/extract-skills")
async def extract_skills(text: str = Form(...)):
    skills = extract_skills_from_resume(text)
    return {"skills": skills}


@router.post("/recommend-careers")
async def recommend_careers(skills: str = Form(...), experience: int = Form(0)):
    skill_list = [s.strip().lower() for s in skills.split(",") if s.strip()]
    careers = generate_career_paths(skill_list, experience)
    return {"careers": careers}


@router.get("/salary")
async def get_salary(job_title: str = Query(...)):
    samples = fetch_salary_samples(job_title)
    return {"salaries": samples}


@router.post("/missing-skills")
async def get_missing_skills(resume_skills: list[str] = Body(...), job_skills: list[str] = Body(...)):
    resume_set = set(s.lower().strip() for s in resume_skills)
    job_set = set(s.lower().strip() for s in job_skills)
    missing = list(job_set - resume_set)
    return {"missing_skills": missing}


@router.post("/chatbot")
async def career_chatbot(request: Request):
    try:
        body = await request.json()
        message = body.get("message")
        if not message:
            return {"answer": "Please provide a valid question."}

        try:
            model = genai.GenerativeModel("gemini-1.5-pro")
            response = model.generate_content(message)
        except Exception as e:
            if "429" in str(e) or "quota" in str(e).lower():
                print("Gemini PRO quota hit — falling back to flash...")
                model = genai.GenerativeModel("gemini-1.5-flash")
                response = model.generate_content(message)
            else:
                raise e

        return {"answer": response.text.strip()}

    except Exception as e:
        return {"answer": f"Error: {str(e)}"}


class CompareJobInput(BaseModel):
    resume_text: str
    job_text: str
    experience: int = 0

def clean_and_split_skills(text):
    if isinstance(text, list):
        items = text
    elif "," in text:
        items = text.split(",")
    else:
        items = text.split()

    return sorted(set(
        s.strip().lower()
        for s in items
        if s.strip() and s.strip().isalpha() and len(s.strip()) > 1
    ))


@router.post("/compare-job")
async def compare_job(data: CompareJobInput):
    resume_skills = set(clean_and_split_skills(extract_skills_from_resume(data.resume_text)))
    job_skills = set(clean_and_split_skills(extract_skills_from_resume(data.job_text)))

    matched = sorted(resume_skills & job_skills)
    missing = sorted(job_skills - resume_skills)
    total = len(job_skills)
    score = int((len(matched) / total) * 100) if total else 0

    exp_pattern = r"(\d+)[\s\-+]*(?:\d+)?\s*(?:years|yrs).+?(?:experience|work)"
    matches = re.findall(exp_pattern, data.job_text.lower())
    job_required_exp = max([int(m) for m in matches], default=0)

    tool_exp_pattern = r"(\d+)[\s\-+]*(?:\d+)?\s*(?:years|yrs).+?with\s+([a-zA-Z\.\+#]+)"
    tool_experience = {
        tool.lower(): int(years)
        for years, tool in re.findall(tool_exp_pattern, data.job_text.lower())
        if years.isdigit()
    }

    return {
        "score": score,
        "matched": matched,
        "missing": missing,
        "resume_experience": data.experience,
        "job_required_experience": job_required_exp,
        "experience_match": data.experience >= job_required_exp,
        "tool_experience": tool_experience
    }


class DocGenRequest(BaseModel):
    resume_text: str
    job_text: str
    full_name: str
    location: str
    phone: str
    email: str
    degree: str
    university: str
    job_title: str
    company_name: str
    company_address: str = ""


@router.post("/generate-docs")
async def generate_docs(data: DocGenRequest):
    today = datetime.today().strftime("%d %B %Y")

    prompt = f"""
    ... your existing prompt ...
    """

    try:
        print("DEBUG: Sending prompt to Gemini model (pro version)")
        model = genai.GenerativeModel("gemini-1.5-pro")
        response = model.generate_content(prompt)
        print("DEBUG: Received response from Gemini (pro version):")
        print(response.text)

    except Exception as e:
        print(f"DEBUG: Exception from Gemini Pro: {str(e)}")
        if "quota" in str(e).lower() or "429" in str(e):
            print("⚠️ Gemini Pro quota exceeded, switching to flash...")
            try:
                model = genai.GenerativeModel("gemini-1.5-flash")
                response = model.generate_content(prompt)
                print("DEBUG: Received response from Gemini (flash version):")
                print(response.text)
            except Exception as e2:
                print(f"🔥 ERROR Gemini Flash fallback failed: {str(e2)}")
                return JSONResponse(status_code=500, content={"error": f"Gemini API error: {str(e2)}"})
        else:
            return JSONResponse(status_code=500, content={"error": f"Gemini API error: {str(e)}"})

    raw = response.text.strip()
    import re
    json_match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not json_match:
        print("🔥 ERROR: No JSON found in Gemini response")
        return JSONResponse(status_code=500, content={"error": "No JSON found in Gemini response"})

    try:
        parsed = json.loads(json_match.group())
    except Exception as e:
        print(f"🔥 ERROR parsing JSON from Gemini response: {str(e)}")
        print("Raw response was:")
        print(raw)
        return JSONResponse(status_code=500, content={"error": f"JSON parsing error: {str(e)}"})

    return {
        "cover_letter": parsed.get("cover_letter", "").strip(),
        "linkedin_message": parsed.get("linkedin_message", "").strip()
    }
