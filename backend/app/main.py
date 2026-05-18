from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

from app.api import routes_upload, routes_exam, routes_template

load_dotenv()

app = FastAPI(
    title="Exam Paper Designer API",
    description="Generate syllabus-aligned question papers from uploaded PDFs.",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(routes_upload.router)
app.include_router(routes_exam.router)
app.include_router(routes_template.router)
