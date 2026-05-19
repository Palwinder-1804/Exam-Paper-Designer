import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List

from app.core.hf_client import HuggingFaceLLM

from app.config import ANSWER_BATCH_SIZE, MAX_PARALLEL_LLM, HF_MODEL

_llm: HuggingFaceLLM | None = None


def _get_llm() -> HuggingFaceLLM:
    global _llm
    if _llm is None:
        _llm = HuggingFaceLLM(
            model=HF_MODEL,
            temperature=0.2,
        )
    return _llm


def _extract_json_array(text: str) -> list:
    cleaned = (text or "").strip()
    cleaned = re.sub(r"^```json\s*", "", cleaned)
    cleaned = re.sub(r"^```\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        data = json.loads(cleaned)
        if isinstance(data, list):
            return data
        if isinstance(data, dict) and "answers" in data:
            return data["answers"]
    except Exception:
        pass
    m = re.search(r"\[.*\]", cleaned, flags=re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except Exception:
            pass
    return []


def _generate_answers_batch(questions: list, start: int, end: int) -> dict:
    """Answer multiple questions in one LLM call."""
    llm = _get_llm()
    batch = questions[start:end]
    lines = []
    for q in batch:
        lines.append(f"Q{q['number']} ({q['marks']}m): {q['question'][:500]}")
    prompt = f"""
Provide model answers for these exam questions. Return ONLY a JSON array:
[
  {{"number": 1, "answer": "..."}},
  ...
]

Questions:
{chr(10).join(lines)}

Rules: concise, accurate. MCQ: state correct option letter + brief reason.
"""
    response = llm.invoke(prompt)
    items = _extract_json_array(getattr(response, "content", str(response)))
    out = {}
    for item in items:
        if isinstance(item, dict) and item.get("number"):
            out[int(item["number"])] = str(item.get("answer", "")).strip()
    # Fallback per missing
    for q in batch:
        if q["number"] not in out:
            r = llm.invoke(f"Brief model answer for Q{q['number']}: {q['question'][:400]}")
            out[q["number"]] = r.content.strip()
    return out


def generate_answers(questions: list) -> list:
    if not questions:
        return []

    answers_map = {}
    n = len(questions)

    # Batch mode: fewer LLM round-trips
    if n > 2:
        batch_size = min(ANSWER_BATCH_SIZE, n)
        ranges = [(i, min(i + batch_size, n)) for i in range(0, n, batch_size)]
        workers = min(MAX_PARALLEL_LLM, len(ranges))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = [
                pool.submit(_generate_answers_batch, questions, s, e) for s, e in ranges
            ]
            for fut in as_completed(futures):
                answers_map.update(fut.result())
    else:
        llm = _get_llm()
        for q in questions:
            r = llm.invoke(f"Brief answer Q{q['number']}: {q['question'][:400]}")
            answers_map[q["number"]] = r.content.strip()

    return [{"number": i, "answer": answers_map.get(i, "")} for i in range(1, n + 1)]
