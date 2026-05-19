from pydantic import BaseModel
from typing import Literal, Optional


class GenerateRequest(BaseModel):
    template: str = "cbse"
    difficulty: Literal["easy", "medium", "hard"] = "medium"
    institution: str = "INSTITUTION NAME"
    subject: str = "SUBJECT"
    exam_date: str = "Date: _______________"
    full_paper: bool = False
    max_questions: Optional[int] = None
    include_answers: bool = True
    export_docx: bool = True
    # False = instant (no Ollama, seconds on i5/8GB). True = LLM (slow on CPU, better wording).
    use_llm: bool = False
