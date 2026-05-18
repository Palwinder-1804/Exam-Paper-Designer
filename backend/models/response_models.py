from pydantic import BaseModel
from typing import Any, Dict, List, Optional


class TemplateSummary(BaseModel):
    id: str
    name: str
    description: str
    duration: str
    maximum_marks: Any
    sections_count: int
    question_types: List[str]


class GenerateResponse(BaseModel):
    paper: str
    answers: str
    pdf: str
    docx: str
    answer_pdf: str
    meta: Dict[str, Any]
