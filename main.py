import os
import uvicorn
from api.routes import router
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="AI Career Recommender")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # restrict to your frontend domain in prod
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include your API router
app.include_router(router)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))  # Get port from environment or default 8000
    uvicorn.run(app, host="0.0.0.0", port=port)
