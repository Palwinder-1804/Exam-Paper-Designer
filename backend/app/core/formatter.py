from typing import Any, Dict, List, Optional


def _header_blocks(
    template_data: Optional[Dict],
    institution: str = "",
    subject: str = "",
    exam_date: str = "",
) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    if institution:
        items.append({"type": "institution", "text": institution.upper()})
    title = (template_data or {}).get("paper_title", "FINAL EXAMINATION")
    items.append({"type": "header_title", "text": title})
    if subject:
        items.append({"type": "subject_line", "text": f"Subject: {subject}"})
    duration = (template_data or {}).get("duration", "")
    max_marks = (template_data or {}).get("maximum_marks", "")
    meta = []
    if duration:
        meta.append(f"Time Allowed: {duration}")
    if max_marks:
        meta.append(f"Maximum Marks: {max_marks}")
    if exam_date:
        meta.append(exam_date)
    if meta:
        items.append({"type": "header_meta", "text": "  |  ".join(meta)})
    items.append(
        {
            "type": "student_fields",
            "text": "Name: _________________________    Roll No.: _________________________    Class/Section: _____________",
        }
    )
    instructions = (template_data or {}).get("instructions", "")
    if instructions:
        items.append({"type": "instructions", "text": f"GENERAL INSTRUCTIONS\n{instructions}"})
    marking = (template_data or {}).get("marking_scheme", {})
    if marking.get("negative_marking"):
        note = marking.get("note", f"Negative marking: {marking['negative_marking']} per wrong answer.")
        items.append({"type": "instructions", "text": note})
    items.append({"type": "divider", "text": "─" * 52})
    return items


def format_paper_blocks(
    questions: List[Dict],
    template_data: Optional[Dict] = None,
    institution: str = "",
    subject: str = "",
    exam_date: str = "",
) -> List[Dict[str, Any]]:
    items = _header_blocks(template_data, institution, subject, exam_date)
    current_section = None
    section_title_shown: set = set()

    for q in questions:
        sec = q["section"]
        if sec != current_section:
            current_section = sec
            stitle = q.get("section_title") or f"SECTION {sec}"
            sinstr = q.get("section_instruction") or ""
            items.append({"type": "section", "text": stitle.upper()})
            if sinstr and sec not in section_title_shown:
                items.append({"type": "section_instruction", "text": sinstr})
            section_title_shown.add(sec)

        items.append(
            {
                "type": "question",
                "number": q["number"],
                "marks": q["marks"],
                "blocks": q.get("blocks")
                or [{"type": "text", "text": q.get("question", "")}],
            }
        )
    return items


def _render_blocks_text(blocks: List[Dict]) -> str:
    lines = []
    for b in blocks:
        if b.get("type") == "text":
            lines.append(b.get("text", ""))
        elif b.get("type") == "sub_questions":
            for sq in b.get("items") or []:
                label = sq.get("label", "a")
                lines.append(f"   ({label}) {sq.get('text', '')}")
        elif b.get("type") == "options":
            for i, opt in enumerate(b.get("options") or []):
                lines.append(f"   ({chr(ord('a') + i)}) {opt}")
        elif b.get("type") == "figure":
            cap = b.get("caption") or "See diagram below."
            lines.append(f"   [{cap}]")
    return "\n".join(lines)


def format_paper(
    questions: List[Dict],
    template_data: Optional[Dict] = None,
    institution: str = "",
    subject: str = "",
    exam_date: str = "",
) -> str:
    blocks = format_paper_blocks(questions, template_data, institution, subject, exam_date)
    lines: List[str] = []
    for item in blocks:
        t = item.get("type")
        text = item.get("text", "")
        if t == "institution":
            lines += ["", text.center(60), ""]
        elif t == "header_title":
            lines += [text.center(60), ""]
        elif t == "subject_line":
            lines.append(text.center(60))
        elif t == "header_meta":
            lines.append(text.center(60))
        elif t == "student_fields":
            lines += ["", text, ""]
        elif t in ("instructions", "section_instruction"):
            lines += ["", text, ""]
        elif t == "divider":
            lines.append(text)
        elif t == "section":
            lines += ["", text, "─" * len(text)]
        elif t == "question":
            qn, marks = item["number"], item["marks"]
            lines.append(f"\nQ{qn}. [{marks} mark{'s' if marks != 1 else ''}]")
            lines.append(_render_blocks_text(item.get("blocks") or []))
    return "\n".join(lines)


def format_answers(answers: List[Dict], template_data: Optional[Dict] = None) -> str:
    title = "ANSWER KEY"
    if template_data:
        title = f"ANSWER KEY — {template_data.get('paper_title', 'EXAMINATION')}"
    lines = [title, "=" * len(title), ""]
    for a in answers:
        lines.append(f"Q{a['number']}. {a['answer']}")
        lines.append("")
    return "\n".join(lines)
