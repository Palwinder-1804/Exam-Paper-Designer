import json
import os
import re
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Optional, Tuple

from app.core.hf_client import HuggingFaceLLM

from app.config import (
    CONTEXT_MAX_CHARS,
    MAX_PARALLEL_LLM,
    MAX_RETRIES,
    HF_MODEL,
    PARALLEL_QUESTIONS,
    QUESTION_BATCH_SIZE,
    RETRIEVAL_K,
)
from app.core.question_validator import similarity, validate_question
from app.services.figure_context_service import (
    FigureAllocator,
    attach_figure_block,
    load_figures,
    needs_diagram,
)
from app.services.retrieval_service import retrieve

FIGURES_JSON_PATH = "app/static/figures/current/figures.json"

_llm: HuggingFaceLLM | None = None
_state_lock = threading.Lock()


def _get_llm() -> HuggingFaceLLM:
    global _llm
    if _llm is None:
        _llm = HuggingFaceLLM(
            model=HF_MODEL,
            temperature=0.35,
            format="json",
        )
    return _llm


def _extract_json_object(text: str) -> Optional[Dict[str, Any]]:
    cleaned = (text or "").strip()
    cleaned = re.sub(r"^```json\s*", "", cleaned)
    cleaned = re.sub(r"^```\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        parsed = json.loads(cleaned)
        return parsed if isinstance(parsed, dict) else None
    except Exception:
        pass
    m = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
    if not m:
        return None
    try:
        parsed = json.loads(m.group(0))
        return parsed if isinstance(parsed, dict) else None
    except Exception:
        return None


def _normalize_fingerprint(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def _blocks_to_question_text(blocks: List[Dict[str, Any]]) -> str:
    parts: List[str] = []
    for b in blocks:
        t = b.get("type")
        if t == "text":
            parts.append(b.get("text", ""))
        elif t == "sub_questions":
            for sq in b.get("items", []):
                label = sq.get("label", "a")
                parts.append(f"({label}) {sq.get('text', '')}")
        elif t == "options":
            for i, opt in enumerate(b.get("options") or []):
                parts.append(f"({chr(ord('a') + i)}) {opt}")
        elif t == "figure":
            cap = b.get("caption") or "See diagram below."
            parts.append(cap)
    return "\n\n".join(p for p in parts if p).strip()


def _clean_figure_references(text: str) -> str:
    text = re.sub(r"\bfig(ure|\.)?\s*\d+([.-]\d+)*\b", "the diagram", text, flags=re.I)
    text = re.sub(r"\bthe\s+the\s+diagram\b", "the diagram", text, flags=re.I)
    text = re.sub(r"\b(in|on|at|by|from|to)\s+the\s+the\s+diagram\b", r"\1 the diagram", text, flags=re.I)
    text = re.sub(r"(?<=^)\bthe\s+diagram\b", "The diagram", text)
    text = re.sub(r"(?<=\.\s)\bthe\s+diagram\b", "The diagram", text)
    return text


def _clean_blocks(blocks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    for b in blocks:
        t = b.get("type")
        if t == "text" and "text" in b:
            b["text"] = _clean_figure_references(b["text"])
        elif t == "sub_questions":
            for sq in b.get("items", []):
                if "text" in sq:
                    sq["text"] = _clean_figure_references(sq["text"])
        elif t == "options":
            opts = b.get("options") or []
            b["options"] = [_clean_figure_references(opt) for opt in opts]
    return blocks


def _parse_response_to_blocks(
    parsed: Optional[Dict],
    item_type: str,
    valid_figure_ids: set,
) -> List[Dict[str, Any]]:
    if not parsed:
        return []

    blocks: List[Dict[str, Any]] = []

    # Case study structured response
    if item_type == "CASE_BASED":
        passage = (parsed.get("passage") or "").strip()
        if passage:
            blocks.append({"type": "text", "text": passage})
        sub_qs = parsed.get("sub_questions") or parsed.get("parts") or []
        items = []
        for i, sq in enumerate(sub_qs):
            if isinstance(sq, dict):
                label = sq.get("label") or sq.get("part") or chr(ord("a") + i)
                text = (sq.get("text") or sq.get("question") or "").strip()
            else:
                label = chr(ord("a") + i)
                text = str(sq).strip()
            if text:
                if not text.endswith("?"):
                    text = text.rstrip(".") + "?"
                items.append({"label": label, "text": text})
        if items:
            blocks.append({"type": "sub_questions", "items": items})

    # Generic blocks array
    raw_blocks = parsed.get("blocks") if not blocks else []
    if isinstance(raw_blocks, list):
        for b in raw_blocks:
            if not isinstance(b, dict):
                continue
            bt = b.get("type")
            if bt == "text" and (b.get("text") or "").strip():
                blocks.append({"type": "text", "text": b["text"].strip()})
            elif bt == "options":
                opts = [str(o).strip() for o in (b.get("options") or []) if str(o).strip()]
                if opts:
                    blocks.append({"type": "options", "options": opts})
            elif bt == "figure":
                fid = (b.get("figure_id") or b.get("id") or "").strip()
                if fid in valid_figure_ids:
                    blocks.append(
                        {
                            "type": "figure",
                            "figure_id": fid,
                            "caption": (b.get("caption") or "").strip() or None,
                        }
                    )

    fig_id = (parsed.get("figure_id") or "").strip()
    if parsed.get("requires_figure") and fig_id in valid_figure_ids:
        if not any(b.get("type") == "figure" for b in blocks):
            blocks = attach_figure_block(
                blocks,
                fig_id,
                (parsed.get("figure_caption") or "").strip(),
            )

    return blocks


def _build_prompt(
    item: Dict[str, Any],
    context: str,
    difficulty: str,
    figure_ids: List[str],
    prev_fps: List[str],
    retry_reason: str = "",
) -> str:
    item_type = item["type"]
    marks = item["marks"]
    options = item.get("options") or (4 if item_type == "MCQ" else 0)

    common_rules = """
STRICT RULES:
- Write a complete, logical examination question — not a syllabus excerpt.
- Do NOT generate questions that are diagram-based or require referring to any figure, graph, chart, or image.
- NEVER mention any figures, diagrams, tables, or illustrations.
- All questions must be fully answerable using plain text only. Do NOT refer to "the diagram", "the graph", "the figure", or any specific figure IDs.
- Must end with a question (? mark) or sub-parts (a), (b) each asking something.
- No copy-paste from context; test understanding/application.
- Output ONLY valid JSON, no markdown.
"""

    if item_type == "CASE_BASED":
        schema = """
{
  "passage": "4-6 sentence case/scenario based on context (original wording)",
  "sub_questions": [
    {"label": "a", "text": "First question with ?"},
    {"label": "b", "text": "Second question with ?"}
  ],
  "fingerprint": "short concept tag"
}
"""
        extra = ""
    elif item_type == "MCQ":
        schema = f"""
{{
  "fingerprint": "...",
  "blocks": [
    {{"type":"text","text":"Question stem ending with ?"}},
    {{"type":"options","options":["opt1","opt2","opt3","opt4"]}}
  ]
}}
"""
        extra = f"- Exactly {options} distinct options."
    else:
        schema = """
{
  "fingerprint": "...",
  "blocks": [{"type":"text","text":"Full question ending with ?"}]
}
"""
        extra = ""

    avoid = f"\nAvoid these concepts already used: {', '.join(prev_fps) or 'none'}."
    retry = f"\nFIX PREVIOUS ERROR: {retry_reason}" if retry_reason else ""

    return f"""
Generate ONE {item_type} question ({marks} marks, {difficulty} difficulty).
Section: {item['section']}

{common_rules}
{extra}
{avoid}
{retry}

JSON schema:
{schema}

Context (syllabus excerpt):
{context[:CONTEXT_MAX_CHARS]}
""".strip()


def _build_batch_prompt(
    items: List[Dict[str, Any]],
    context: str,
    difficulty: str,
    figure_ids: List[str],
    prev_fps: List[str],
) -> str:
    item = items[0]
    n = len(items)
    item_type = item["type"]
    marks = item["marks"]
    options = item.get("options") or (4 if item_type == "MCQ" else 0)

    common_rules = """
STRICT RULES for each question:
- Write a complete, logical examination question — not a syllabus excerpt.
- Do NOT generate questions that are diagram-based or require referring to any figure, graph, chart, or image.
- NEVER mention any figures, diagrams, tables, or illustrations.
- All questions must be fully answerable using plain text only. Do NOT refer to "the diagram", "the graph", "the figure", or any specific figure IDs.
- Must end with a question (? mark) or sub-parts (a), (b) each asking something.
- No copy-paste from context; test understanding/application.
"""

    if item_type == "CASE_BASED":
        schema = """
{
  "passage": "4-6 sentence case/scenario based on context",
  "sub_questions": [
    {"label": "a", "text": "First question with ?"},
    {"label": "b", "text": "Second question with ?"}
  ],
  "fingerprint": "short concept tag"
}
"""
    elif item_type == "MCQ":
        schema = f"""
{{
  "fingerprint": "...",
  "blocks": [
    {{"type":"text","text":"Question stem ending with ?"}},
    {{"type":"options","options":["opt1","opt2","opt3","opt4"]}}
  ]
}}
"""
    else:
        schema = """
{
  "fingerprint": "...",
  "blocks": [{"type":"text","text":"Full question ending with ?"}]
}
"""

    avoid = f"Avoid these concepts: {', '.join(prev_fps[-8:]) or 'none'}."

    return f"""
Generate exactly {n} distinct {item_type} questions ({marks} marks each, {difficulty} difficulty).
Section: {item['section']}

Return ONLY JSON matching this format:
{{
  "questions": [
    {schema.strip()}
  ]
}}
(where the list contains exactly {n} question objects matching the schema)

{common_rules}
{avoid}

Context:
{context[:CONTEXT_MAX_CHARS]}
""".strip()


def _extract_json_array(text: str) -> List[Dict]:
    cleaned = (text or "").strip()
    cleaned = re.sub(r"^```json\s*", "", cleaned)
    cleaned = re.sub(r"^```\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        data = json.loads(cleaned)
        if isinstance(data, dict) and isinstance(data.get("questions"), list):
            return data["questions"]
        if isinstance(data, list):
            return data
    except Exception:
        pass
    m = re.search(r"\[.*\]", cleaned, flags=re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except Exception:
            pass
    return []


def _finalize_question(
    item: Dict,
    parsed: Optional[Dict],
    allocator: FigureAllocator,
    used_fingerprints: List[str],
    used_texts: List[str],
) -> Optional[Dict[str, Any]]:
    """Validate and post-process one parsed question; returns None if invalid."""
    item_type = item["type"]
    valid_ids = set(allocator.available_ids)
    blocks = _parse_response_to_blocks(parsed, item_type, valid_ids)
    if not blocks:
        return None
    blocks = _clean_blocks(blocks)

    text = _blocks_to_question_text(blocks)
    fp = _normalize_fingerprint((parsed or {}).get("fingerprint", "") or text[:100])

    with _state_lock:
        if fp in used_fingerprints or any(similarity(text, t) > 0.72 for t in used_texts):
            return None

    want_fig = False

    ok, _ = validate_question(blocks, item_type, require_figure=want_fig and bool(valid_ids))
    if not ok:
        return None

    with _state_lock:
        used_fingerprints.append(fp)
        used_texts.append(text)

    return {
        "section": item["section"],
        "section_title": item.get("section_title"),
        "section_instruction": item.get("section_instruction"),
        "marks": item["marks"],
        "question": text,
        "blocks": blocks,
    }


def _generate_batch(
    items: List[Dict[str, Any]],
    context: str,
    allocator: FigureAllocator,
    used_fingerprints: List[str],
    used_texts: List[str],
    difficulty: str,
) -> List[Dict[str, Any]]:
    if len(items) == 1:
        return [_generate_one(items[0], context, allocator, used_fingerprints, used_texts, difficulty)]

    llm = _get_llm()
    response = llm.invoke(
        _build_batch_prompt(items, context, difficulty, allocator.available_ids, used_fingerprints)
    )
    parsed_list = _extract_json_array(getattr(response, "content", str(response)))

    results: List[Optional[Dict]] = []
    for i, item in enumerate(items):
        parsed = parsed_list[i] if i < len(parsed_list) and isinstance(parsed_list[i], dict) else None
        q = _finalize_question(item, parsed, allocator, used_fingerprints, used_texts)
        if q is None:
            q = _generate_one(item, context, allocator, used_fingerprints, used_texts, difficulty)
        results.append(q)
    return results


def _group_plan(plan: List[Dict]) -> List[List[Dict]]:
    batches: List[List[Dict]] = []
    i = 0
    while i < len(plan):
        item = plan[i]
        if item.get("type") == "CASE_BASED":
            batches.append([item])
            i += 1
            continue
        key = f"{item.get('section', '')}|{item['type']}"
        group = [item]
        j = i + 1
        while j < len(plan) and len(group) < QUESTION_BATCH_SIZE:
            nxt = plan[j]
            if f"{nxt.get('section', '')}|{nxt['type']}" == key:
                group.append(nxt)
                j += 1
            else:
                break
        batches.append(group)
        i = j
    return batches


def _generate_one(
    item: Dict[str, Any],
    context: str,
    allocator: FigureAllocator,
    used_fingerprints: List[str],
    used_texts: List[str],
    difficulty: str,
) -> Dict[str, Any]:
    llm = _get_llm()
    item_type = item["type"]
    valid_ids = set(allocator.available_ids)
    last_reason = ""

    for attempt in range(MAX_RETRIES):
        prompt = _build_prompt(
            item,
            context,
            difficulty,
            allocator.available_ids,
            used_fingerprints[-8:],
            last_reason,
        )
        response = llm.invoke(prompt)
        parsed = _extract_json_object(getattr(response, "content", str(response)))
        blocks = _parse_response_to_blocks(parsed, item_type, valid_ids)

        if not blocks:
            last_reason = "Invalid JSON or empty blocks"
            continue

        blocks = _clean_blocks(blocks)
        text = _blocks_to_question_text(blocks)
        fp = _normalize_fingerprint(
            (parsed or {}).get("fingerprint", "") or text[:100]
        )

        with _state_lock:
            dup = fp in used_fingerprints or any(
                similarity(text, t) > 0.72 for t in used_texts
            )
        if dup:
            last_reason = "Duplicate or too similar to another question"
            continue

        want_fig = False

        ok, reason = validate_question(
            blocks,
            item_type,
            require_figure=want_fig and bool(valid_ids),
        )
        if not ok:
            last_reason = reason
            continue

        with _state_lock:
            used_fingerprints.append(fp)
            used_texts.append(text)

        return {
            "section": item["section"],
            "section_title": item.get("section_title"),
            "section_instruction": item.get("section_instruction"),
            "marks": item["marks"],
            "question": text,
            "blocks": blocks,
        }

    # Fallback — simple but valid
    fallback_text = (
        f"Explain an important concept from the syllabus related to {item['section']} "
        f"in the context of the uploaded material. ({item['marks']} marks)"
    )
    blocks = [{"type": "text", "text": fallback_text}]
    return {
        "section": item["section"],
        "section_title": item.get("section_title"),
        "section_instruction": item.get("section_instruction"),
        "marks": item["marks"],
        "question": fallback_text,
        "blocks": blocks,
    }


def generate_questions(plan: List[Dict], difficulty: str = "medium") -> List[Dict]:
    allocator = FigureAllocator()
    used_fingerprints: List[str] = []
    used_texts: List[str] = []

    batches = _group_plan(plan)

    # Count how many batches exist per (section, type) key
    key_batch_counts = {}
    for g in batches:
        key = f"{g[0].get('section', '')}|{g[0]['type']}"
        key_batch_counts[key] = key_batch_counts.get(key, 0) + 1

    # Retrieve a larger pool of diverse chunks per key
    key_contexts = {}
    for key, count in key_batch_counts.items():
        # Retrieve count * RETRIEVAL_K chunks to get diverse topics
        chunks = retrieve(key, k=max(RETRIEVAL_K, count * RETRIEVAL_K))
        key_contexts[key] = chunks

    # Keep track of how many batches of each key we have processed so far
    key_batch_indices = {}
    key_indices_lock = threading.Lock()

    batch_results: Dict[int, List[Dict]] = {}

    def run_batch(batch_idx: int, group: List[Dict]) -> Tuple[int, List[Dict]]:
        key = f"{group[0].get('section', '')}|{group[0]['type']}"

        # Get the index of this batch for this key in a thread-safe manner
        with key_indices_lock:
            b_idx = key_batch_indices.get(key, 0)
            key_batch_indices[key] = b_idx + 1

        chunks = key_contexts[key]
        start = b_idx * RETRIEVAL_K
        end = start + RETRIEVAL_K
        batch_chunks = chunks[start:end]
        if not batch_chunks:
            batch_chunks = chunks[:RETRIEVAL_K]

        ctx = "\n".join(batch_chunks)
        return batch_idx, _generate_batch(
            group, ctx, allocator, used_fingerprints, used_texts, difficulty
        )

    if PARALLEL_QUESTIONS and len(batches) > 1:
        workers = min(MAX_PARALLEL_LLM, len(batches))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {
                pool.submit(run_batch, bi, g): bi for bi, g in enumerate(batches)
            }
            for fut in as_completed(futures):
                bi, qs = fut.result()
                batch_results[bi] = qs
    else:
        for bi, g in enumerate(batches):
            batch_results[bi] = run_batch(bi, g)[1]

    questions: List[Dict] = []
    for bi in range(len(batches)):
        questions.extend(batch_results[bi])

    for i, q in enumerate(questions):
        q["number"] = i + 1
    return questions
