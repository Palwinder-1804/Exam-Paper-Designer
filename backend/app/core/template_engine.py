import json
import os
from typing import Any, Dict, List

from app.config import DEFAULT_MAX_QUESTIONS

TEMPLATES_DIR = "app/templates"


def list_templates() -> List[Dict[str, Any]]:
    summaries = []
    for fname in sorted(os.listdir(TEMPLATES_DIR)):
        if not fname.endswith(".json"):
            continue
        tid = fname[:-5]
        data = load_template(tid)
        types = sorted({s.get("type", "SHORT") for s in data.get("sections", [])})
        summaries.append(
            {
                "id": tid,
                "name": data.get("template_name", tid.upper()),
                "description": data.get("description", data.get("instructions", "")),
                "duration": data.get("duration", ""),
                "maximum_marks": data.get("maximum_marks", ""),
                "paper_title": data.get("paper_title", ""),
                "sections_count": len(data.get("sections", [])),
                "question_types": types,
                "category": data.get("category", "general"),
            }
        )
    return summaries


def load_template(name: str) -> Dict[str, Any]:
    path = os.path.join(TEMPLATES_DIR, f"{name}.json")
    if not os.path.exists(path):
        raise FileNotFoundError(f"Template '{name}' not found")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _scale_section_counts(sections: List[Dict], cap: int) -> List[int]:
    total = sum(max(0, s.get("count", 0)) for s in sections)
    if total <= cap:
        return [s.get("count", 0) for s in sections]

    raw = [s.get("count", 0) for s in sections]
    scaled = [max(1, round(c * cap / total)) for c in raw]
    diff = cap - sum(scaled)
    idx = 0
    while diff != 0 and sections:
        i = idx % len(scaled)
        if diff > 0:
            scaled[i] += 1
            diff -= 1
        elif scaled[i] > 1:
            scaled[i] -= 1
            diff += 1
        idx += 1
        if idx > len(scaled) * 20:
            break
    return scaled


def build_question_plan(
    template: Dict[str, Any],
    *,
    full_paper: bool = False,
    max_questions: int | None = None,
) -> List[Dict[str, Any]]:
    sections = template.get("sections", [])
    cap = max_questions
    if cap is None:
        gen_cfg = template.get("generation", {})
        cap = gen_cfg.get("max_questions", DEFAULT_MAX_QUESTIONS)
        if full_paper:
            cap = gen_cfg.get("full_max_questions", sum(s.get("count", 0) for s in sections))

    counts = (
        [s.get("count", 0) for s in sections]
        if full_paper
        else _scale_section_counts(sections, cap)
    )

    plan = []
    for section, count in zip(sections, counts):
        section_label = section.get("section") or section.get("label") or "A"
        q_type = section.get("type") or "SHORT"
        marks = section.get("marks") or 1
        section_title = section.get("section_title") or f"Section {section_label}"
        section_instruction = section.get("section_instruction", "")
        options = section.get("options", 4 if q_type == "MCQ" else 0)

        for _ in range(count):
            plan.append(
                {
                    "section": section_label,
                    "section_title": section_title,
                    "section_instruction": section_instruction,
                    "type": q_type,
                    "marks": marks,
                    "options": options,
                }
            )
    return plan
