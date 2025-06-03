# backend/serpapi_salary.py

import requests
import os
from dotenv import load_dotenv

load_dotenv()
SERPAPI_KEY = os.getenv("SERPAPI_KEY")

def fetch_salary_samples(job_title, location="United States"):
    url = "https://serpapi.com/search.json"
    params = {
        "engine": "google_jobs",
        "q": f"{job_title} in {location}",
        "api_key": SERPAPI_KEY,
    }

    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        data = response.json()

        jobs = data.get("jobs_results", [])
        samples = []

        for job in jobs[:5]:  # limit to top 5 listings
            title = job.get("title", "")
            company = job.get("company_name", "")
            salary = job.get("salary")

            # Check job_highlights
            if not salary and isinstance(job.get("job_highlights"), dict):
                for cat, items in job["job_highlights"].items():
                    for item in items:
                        if "$" in item or "₹" in item:
                            salary = item
                            break

            # Scrape from description
            if not salary and "description" in job:
                lines = job["description"].split("\n")
                for line in lines:
                    if "$" in line or "₹" in line:
                        salary = line.strip()
                        break

            if salary:
                samples.append(f"{title} at {company} — {salary}")
        return samples
    except Exception as e:
        print(f"❌ Error fetching salary: {e}")
        return []
