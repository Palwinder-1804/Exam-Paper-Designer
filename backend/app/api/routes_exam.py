import os
import time
import uuid
from concurrent.futures import ThreadPoolExecutor

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.config import DB_PATH, OUTPUT_DIR
from app.core.template_engine import load_template, build_question_plan
from app.core.question_generator import generate_questions
from app.core.answer_generator import generate_answers
from app.core.instant_generator import generate_questions_instant, generate_answers_instant
from app.core.formatter import format_paper, format_paper_blocks, format_answers
from app.services.export_service import export_pdf, export_docx
from models.request_models import GenerateRequest

router = APIRouter(tags=["exam"])


@router.post("/generate")
def generate(body: GenerateRequest):
    t0 = time.perf_counter()
    index_path = os.path.join(DB_PATH, "index.faiss")
    if not os.path.exists(index_path):
        raise HTTPException(status_code=400, detail="Upload a syllabus PDF first.")

    try:
        template_data = load_template(body.template)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Template '{body.template}' not found.")

    plan = build_question_plan(
        template_data,
        full_paper=body.full_paper,
        max_questions=body.max_questions,
    )
    if not plan:
        raise HTTPException(status_code=400, detail="Template has no questions configured.")

    t_plan = time.perf_counter()
    if body.use_llm:
        questions = generate_questions(plan, difficulty=body.difficulty)
    else:
        questions = generate_questions_instant(plan, difficulty=body.difficulty)
    t_questions = time.perf_counter()

    answers = []
    answer_key = ""
    answer_pdf = ""
    if body.include_answers:
        if body.use_llm:
            answers = generate_answers(questions)
        else:
            answers = generate_answers_instant(questions)
        answer_key = format_answers(answers, template_data)
    t_answers = time.perf_counter()

    paper_text = format_paper(
        questions,
        template_data,
        institution=body.institution,
        subject=body.subject,
        exam_date=body.exam_date,
    )
    paper_blocks = format_paper_blocks(
        questions,
        template_data,
        institution=body.institution,
        subject=body.subject,
        exam_date=body.exam_date,
    )
    t_format = time.perf_counter()

    for q in questions:
        q.pop("_instant", None)
        q.pop("_instant_mcq_correct_index", None)

    uid = uuid.uuid4().hex[:8]

    def do_pdf():
        return export_pdf(paper_blocks, f"paper_{uid}.pdf")

    def do_docx():
        return export_docx(paper_blocks, f"paper_{uid}.docx")

    def do_answer_pdf():
        return export_pdf(answer_key, f"answers_{uid}.pdf") if answer_key else ""

    with ThreadPoolExecutor(max_workers=3) as pool:
        fut_pdf = pool.submit(do_pdf)
        fut_docx = pool.submit(do_docx) if body.export_docx else None
        fut_ans = pool.submit(do_answer_pdf) if body.include_answers and answer_key else None
        pdf_path = fut_pdf.result()
        docx_path = fut_docx.result() if fut_docx else ""
        answer_pdf = fut_ans.result() if fut_ans else ""

    t_end = time.perf_counter()

    return {
        "paper": paper_text,
        "answers": answer_key,
        "pdf": pdf_path,
        "docx": docx_path,
        "answer_pdf": answer_pdf,
        "meta": {
            "template": body.template,
            "questions_generated": len(questions),
            "full_paper": body.full_paper,
            "difficulty": body.difficulty,
            "include_answers": body.include_answers,
            "use_llm": body.use_llm,
            "timing_seconds": {
                "questions": round(t_questions - t_plan, 1),
                "answers": round(t_answers - t_questions, 1) if body.include_answers else 0,
                "export": round(t_end - t_format, 1),
                "total": round(t_end - t0, 1),
            },
        },
    }


@router.get("/download/{filename}")
def download_file(filename: str):
    safe = os.path.basename(filename)
    path = os.path.join(OUTPUT_DIR, safe)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="File not found")
    media = "application/pdf" if safe.endswith(".pdf") else (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
    return FileResponse(path, filename=safe, media_type=media)
