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
from fastapi import UploadFile, File, Form
from fastapi.responses import JSONResponse
from typing import Optional
import re
import tempfile
import docx2txt
import PyPDF2
import io

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


def extract_text_from_pdf(file_bytes: bytes) -> str:
    text = ""
    try:
        reader = PyPDF2.PdfReader(io.BytesIO(file_bytes))
        for page in reader.pages:
            text += page.extract_text() or ""
    except Exception as e:
        print("PDF extraction error:", e)
    return text

def extract_text_from_docx(file_bytes: bytes) -> str:
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".docx") as tmp:
            tmp.write(file_bytes)
            tmp_path = tmp.name
        text = docx2txt.process(tmp_path)
    except Exception as e:
        print("DOCX extraction error:", e)
        text = ""
    return text

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

import logging
from fastapi import UploadFile, File, Form
from fastapi.responses import JSONResponse
from typing import Optional

@router.post("/compare-job")
async def compare_job(
    resume_file: UploadFile = File(...),
    job_text: str = Form(...),
    experience: Optional[int] = Form(0)
):
    try:
        # Read bytes from the uploaded file
        file_bytes = await resume_file.read()

        # Extract text depending on file type
        content = ""
        if resume_file.filename.lower().endswith(".pdf"):
            content = extract_text_from_pdf(file_bytes)
        elif resume_file.filename.lower().endswith(".docx"):
            content = extract_text_from_docx(file_bytes)
        else:
            return JSONResponse(status_code=400, content={"error": "Unsupported file format"})

        # Defensive check if content is empty after extraction
        if not content.strip():
            return JSONResponse(status_code=400, content={"error": "Failed to extract text from resume"})

        # Process skills
        resume_skills = set(clean_and_split_skills(extract_skills_from_resume(content)))
        job_skills = set(clean_and_split_skills(extract_skills_from_resume(job_text))) if job_text else set()

        matched = sorted(resume_skills & job_skills)
        missing = sorted(job_skills - resume_skills)
        total = len(job_skills)
        score = int((len(matched) / total) * 100) if total else 0

        exp_pattern = r"(\d+)[\s\-+]*(?:\d+)?\s*(?:years|yrs).+?(?:experience|work)"
        matches = re.findall(exp_pattern, job_text.lower())
        job_required_exp = max([int(m) for m in matches], default=0)

        tool_exp_pattern = r"(\d+)[\s\-+]*(?:\d+)?\s*(?:years|yrs).+?with\s+([a-zA-Z\.\+#]+)"
        tool_experience = {
            tool.lower(): int(years)
            for years, tool in re.findall(tool_exp_pattern, job_text.lower())
            if years.isdigit()
        }

        return {
            "score": score,
            "matched": matched,
            "missing": missing,
            "resume_experience": experience,
            "job_required_experience": job_required_exp,
            "experience_match": experience >= job_required_exp,
            "tool_experience": tool_experience
        }

    except Exception as e:
        logging.error(f"Error processing /compare-job: {e}", exc_info=True)
        return JSONResponse(status_code=500, content={"error": "Internal Server Error"})


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
You are an AI job application assistant. Your task is to:
1. Extract key highlights from the resume, such as project impact, quantifiable results, tools used, certifications, and domain expertise.
2. Use those highlights to create a professional, ATS-friendly cover letter that aligns with the job description and the company's goals.
3. Make sure formatting is simple, clean, and keyword-optimized for Applicant Tracking Systems (ATS). Avoid decorative styling, fonts, or images.
4. Also write a concise and polite 300-character LinkedIn message requesting a referral. Use a general default message such as:
   "Hi, I'm excited to apply for the {data.job_title} role at {data.company_name}. With my background in {data.degree} from {data.university}, I’d really appreciate a quick chat or a referral if you’re open to it. Thank you!"

Here’s the input context you should use:

---
**Resume Summary**:
{data.resume_text}

**Job Description**:
{data.job_text}

**User Details**:
Full Name: {data.full_name}  
Location: {data.location}  
Phone: {data.phone}  
Email: {data.email}  
Degree: {data.degree}  
University: {data.university}  
Job Title: {data.job_title}  
Company Name: {data.company_name}  
Company Address: {data.company_address or '[Company Address]'}  
Date: {today}

---
Respond ONLY in the following raw JSON format:
```json
{{
  "cover_letter": "<Well-structured, ATS-optimized cover letter with resume highlights>",
  "linkedin_message": "<300 character professional referral message>"
}}
```
"""
    try:
        try:
            model = genai.GenerativeModel("gemini-1.5-pro")
            response = model.generate_content(prompt)
        except Exception as e:
            if "quota" in str(e).lower() or "429" in str(e):
                print("⚠️ Gemini Pro quota exceeded, switching to flash...")
                model = genai.GenerativeModel("gemini-1.5-flash")
                response = model.generate_content(prompt)
            else:
                raise

        raw = response.text.strip()
        json_block = raw[raw.find("{"):raw.rfind("}") + 1]
        parsed = json.loads(json_block)

        return {
            "cover_letter": parsed.get("cover_letter", "").strip(),
            "linkedin_message": parsed.get("linkedin_message", "").strip()
        }

    except Exception as e:
        print("🔥 ERROR in /generate-docs:", str(e))
        return JSONResponse(status_code=500, content={"error": f"Internal Server Error: {str(e)}"})
