"""
CPU-friendly paper generation in ~1–3 seconds (no Ollama / no LLM).

Uses FAISS retrieval + heuristics. Filters copyright/PREFACE junk and builds
sentence-based MCQs so options are not repeated nonsense.
"""
from __future__ import annotations

import hashlib
import re
from typing import Any, Dict, List, Optional, Set, Tuple

from app.services.figure_context_service import FigureAllocator, attach_figure_block, needs_diagram
from app.services.retrieval_service import retrieve

_CHUNK_CACHE: Dict[str, List[str]] = {}
_FILTERED_CACHE: Dict[str, List[str]] = {}

_JUNK_LINE = re.compile(
    r"Printed on \d+\s*GSM|ISBN|ALL RIGHTS RESERVED|PREFACE|Textbook Development Committee|"
    r"Amit Printing|Publication Division|NCERT watermark|boxshadow|Sri Aurobindo Marg|"
    r"Mathura-\s*281|National Council of Educational Research|No part of this publication|"
    r"First Edition|Reprint|Cartography|design and layout|Phone:\s*Fax:|e-mail:|"
    r"Acknowledgements|Foreword|ISBN\s*81-",
    re.I,
)

_BOILER_ONLY = re.compile(
    r"^(SCIENCE|MATHEMATICS|PHYSICS|CHEMISTRY|BIOLOGY)\s*\d+\s*$",
    re.I,
)


def _raw_chunks(key: str, pool_size: int = 55) -> List[str]:
    if key not in _CHUNK_CACHE:
        _CHUNK_CACHE[key] = retrieve(key, k=pool_size)
    return _CHUNK_CACHE[key]


def _chunk_quality(text: str) -> float:
    t = (text or "").strip()
    if len(t) < 110:
        return -100.0
    if _JUNK_LINE.search(t):
        return -100.0
    if len(t) > 1200 and _JUNK_LINE.search(t[:400]):
        return -80.0
    digit_ratio = len(re.findall(r"\d", t)) / max(len(t), 1)
    if digit_ratio > 0.22 and len(re.findall(r"[a-zA-Z]{4,}", t)) < 8:
        return -50.0

    score = min(len(t), 900) / 900.0 * 6.0
    if re.search(r"\b(Fill in|exercises?|Mark\s+[’']T|True or False|Why |How |What |Which )\b", t, re.I):
        score += 4.0
    if re.search(
        r"\b(heat|light|current|cell|atom|force|energy|motion|speed|circuit|lens|mirror|"
        r"plant|animal|digestion|photosynthesis|acid|base|reaction|sound|wave|electric)\b",
        t,
        re.I,
    ):
        score += 3.0
    if "?" in t:
        score += 1.5
    if re.search(r"\b(fig\.|figure|diagram|graph)\b", t, re.I):
        score += 1.0
    return score


def _syllabus_chunks(key: str) -> List[str]:
    """Deduplicate, drop junk, sort by educational signal."""
    if key in _FILTERED_CACHE:
        return _FILTERED_CACHE[key]

    raw = _raw_chunks(key, pool_size=55)
    seen: Set[str] = set()
    scored: List[Tuple[float, str]] = []
    for ch in raw:
        c = re.sub(r"\s+", " ", (ch or "").strip())
        if len(c) < 110:
            continue
        sig = c[:160].lower()
        if sig in seen:
            continue
        q = _chunk_quality(c)
        if q < 0:
            continue
        seen.add(sig)
        scored.append((q, c))

    scored.sort(key=lambda x: -x[0])
    out = [t for _, t in scored[:28]]
    if not out:
        out = [re.sub(r"\s+", " ", c).strip() for c in raw if len(c.strip()) > 80][:8]
    _FILTERED_CACHE[key] = out
    return out


def _sentences(text: str) -> List[str]:
    t = re.sub(r"\s+", " ", (text or "").strip())
    parts = re.split(r"(?<=[.!?])\s+", t)
    out: List[str] = []
    for p in parts:
        p = p.strip()
        if len(p) < 45 or len(p) > 260:
            continue
        if _JUNK_LINE.search(p) or _BOILER_ONLY.match(p):
            continue
        if re.match(r"^\(?[ivx]+\)?\s*$", p, re.I):
            continue
        out.append(p)
    return out[:12]


def _pick_chunk_index(clean: List[str], seed: int, avoid: Optional[int] = None) -> int:
    if not clean:
        return 0
    idx = seed % len(clean)
    if avoid is not None and len(clean) > 1 and idx == avoid:
        idx = (idx + 1) % len(clean)
    return idx


def _statement_options_from_chunks(
    passage_chunk: str,
    all_clean: List[str],
    passage_idx: int,
    options: int,
    q_index: int,
) -> Tuple[str, List[str], str]:
    """
    Build stem + list of option strings (first = correct).
    Correct = best factual sentence from passage chunk; wrong = sentences from other chunks.
    """
    sents = _sentences(passage_chunk)
    body = _snippet(passage_chunk, 420)
    if sents:
        correct = sents[0]
    else:
        correct = body[:200] + ("…" if len(body) > 200 else "")

    wrong_pool: List[str] = []
    for j, other in enumerate(all_clean):
        if j == passage_idx:
            continue
        for s in _sentences(other):
            if _similar_sentence(correct, s):
                continue
            wrong_pool.append(s)
        if len(wrong_pool) >= options + 12:
            break

    if len(wrong_pool) < options - 1:
        for s in _sentences(passage_chunk)[1:]:
            if not _similar_sentence(correct, s):
                wrong_pool.append(s)
            if len(wrong_pool) >= options + 12:
                break

    start = (q_index * 3) % max(1, len(wrong_pool))
    wrongs: List[str] = []
    for k in range(start, start + options * 4):
        if len(wrongs) >= options - 1:
            break
        if not wrong_pool:
            break
        cand = wrong_pool[k % len(wrong_pool)]
        if cand not in wrongs and not _similar_sentence(correct, cand):
            wrongs.append(cand)

    while len(wrongs) < options - 1:
        wrongs.append(
            "None of the statements above can be verified from the given passage alone."
        )

    stem = (
        "Read the following from your syllabus and answer the multiple-choice question.\n\n"
        f"Passage:\n{_snippet(body, 400)}\n\n"
        "Which statement is best supported by the passage above?"
    )
    opts = [correct] + wrongs[: options - 1]
    return stem, opts, correct


def _similar_sentence(a: str, b: str) -> bool:
    wa = set(re.findall(r"[a-zA-Z]{4,}", a.lower()))
    wb = set(re.findall(r"[a-zA-Z]{4,}", b.lower()))
    if not wa or not wb:
        return False
    j = len(wa & wb) / max(1, len(wa | wb))
    return j > 0.55


def _snippet(text: str, max_len: int = 420) -> str:
    t = re.sub(r"\s+", " ", (text or "").strip())
    if len(t) <= max_len:
        return t
    return t[: max_len - 3].rsplit(" ", 1)[0] + "..."


def _numbers_in(text: str) -> List[float]:
    nums: List[float] = []
    for m in re.finditer(r"\b(\d+\.?\d*)\b", text):
        try:
            nums.append(float(m.group(1)))
        except ValueError:
            pass
    return nums


def _build_mcq(
    chunk: str,
    chunk_idx: int,
    all_clean: List[str],
    options: int,
    allocator: FigureAllocator,
    want_figure: bool,
    q_index: int,
) -> Tuple[List[Dict[str, Any]], str]:
    stem, opts, _ = _statement_options_from_chunks(chunk, all_clean, chunk_idx, options, q_index)
    blocks: List[Dict[str, Any]] = [{"type": "text", "text": stem}]
    if want_figure and allocator.available_ids:
        fid = allocator.allocate(None)
        if fid:
            blocks = attach_figure_block(
                blocks, fid, "Refer to the diagram below.", before_subquestions=True
            )
    blocks.append({"type": "options", "options": opts})
    return blocks, stem


def _build_case(
    chunk_a: str,
    chunk_b: str,
    allocator: FigureAllocator,
) -> List[Dict[str, Any]]:
    p1, p2 = _snippet(chunk_a, 400), _snippet(chunk_b, 400)
    passage = (
        "Read the following case based on two excerpts from the textbook.\n\n"
        f"Excerpt A:\n{p1}\n\n"
        f"Excerpt B:\n{p2}"
    )
    blocks: List[Dict[str, Any]] = [{"type": "text", "text": passage}]
    if allocator.available_ids:
        fid = allocator.allocate(None)
        if fid:
            blocks = attach_figure_block(
                blocks, fid, "Use the diagram if relevant.", before_subquestions=False
            )
    blocks.append(
        {
            "type": "sub_questions",
            "items": [
                {
                    "label": "a",
                    "text": "List two scientific facts or processes mentioned in Excerpt A. (2 marks)",
                },
                {
                    "label": "b",
                    "text": "How does Excerpt B add a new idea, example, or application compared to Excerpt A? (2 marks)",
                },
            ],
        }
    )
    return blocks


def _blocks_to_plain(blocks: List[Dict[str, Any]]) -> str:
    parts: List[str] = []
    for b in blocks:
        if b.get("type") == "text":
            parts.append(b.get("text", ""))
        elif b.get("type") == "sub_questions":
            for sq in b.get("items", []):
                parts.append(f"({sq.get('label','a')}) {sq.get('text','')}")
        elif b.get("type") == "options":
            for i, opt in enumerate(b.get("options") or []):
                parts.append(f"({chr(ord('a') + i)}) {opt}")
        elif b.get("type") == "figure":
            parts.append(b.get("caption") or "See figure.")
    return "\n\n".join(p for p in parts if p).strip()


def generate_questions_instant(plan: List[Dict[str, Any]], difficulty: str = "medium") -> List[Dict[str, Any]]:
    allocator = FigureAllocator()
    built: Dict[int, Dict[str, Any]] = {}
    per_key_state: Dict[str, Dict[str, Any]] = {}

    def state_for(key: str) -> Dict[str, Any]:
        if key not in per_key_state:
            clean = _syllabus_chunks(key)
            per_key_state[key] = {"clean": clean, "cursor": 0}
        return per_key_state[key]

    for i, item in enumerate(plan):
        key = f"{item.get('section', '')}|{item['type']}"
        st = state_for(key)
        clean: List[str] = st["clean"]
        if not clean:
            clean = ["No usable syllabus paragraphs after filtering. Try a different PDF or use AI mode."]

        seed = int(hashlib.md5(f"{key}|{i}".encode()).hexdigest(), 16)
        cidx = _pick_chunk_index(clean, seed + st["cursor"], avoid=None)
        st["cursor"] = (st["cursor"] + 1) % max(1, len(clean))
        chunk = clean[cidx]

        cidx_b = _pick_chunk_index(clean, seed + 7 + i, avoid=cidx)
        if qtype == "CASE_BASED" and len(clean) > 1:
            best_j, best_q = cidx_b, -1.0
            for j, ch in enumerate(clean):
                if j == cidx:
                    continue
                qv = _chunk_quality(ch)
                if qv > best_q:
                    best_q, best_j = qv, j
            cidx_b = best_j
        chunk_b = clean[cidx_b]

        qtype = item.get("type") or "SHORT"
        marks = item.get("marks") or 1
        options = item.get("options") or (4 if qtype == "MCQ" else 0)
        want_fig = needs_diagram(qtype, chunk) and bool(allocator.available_ids)

        blocks: List[Dict[str, Any]] = []

        if qtype == "MCQ":
            blocks, _ = _build_mcq(chunk, cidx, clean, options, allocator, want_fig, i)
        elif qtype == "NUMERICAL":
            nums = _numbers_in(chunk)
            if len(nums) >= 2:
                a, b = nums[0], nums[1]
                stem = (
                    f"The syllabus excerpt below contains the numeric values {a} and {b}. "
                    f"Compute the absolute difference |{a} - {b}| and write the result as your answer.\n\n"
                    f"{_snippet(chunk, 320)}"
                )
            elif len(nums) == 1:
                stem = (
                    f"The excerpt below mentions the number {nums[0]}. "
                    f"State this value as your numerical answer and briefly describe what it refers to in the context.\n\n"
                    f"{_snippet(chunk, 320)}"
                )
            else:
                stem = (
                    "Read the passage and give one numerical estimate (integer) for a quantity implied there, "
                    "with one sentence of justification.\n\n"
                    f"{_snippet(chunk, 360)}"
                )
            blocks = [{"type": "text", "text": stem}]
            if want_fig and allocator.available_ids:
                fid = allocator.allocate(None)
                if fid:
                    blocks = attach_figure_block(
                        blocks, fid, "Refer to the diagram if needed.", before_subquestions=True
                    )
        elif qtype == "CASE_BASED":
            blocks = _build_case(chunk, chunk_b, allocator)
        elif qtype == "VERY_SHORT":
            lead = _sentences(chunk)
            focus = lead[0] if lead else _snippet(chunk, 200)
            blocks = [
                {
                    "type": "text",
                    "text": (
                        "Answer in 40–60 words.\n\n"
                        f"Explain or define the idea expressed in: “{focus}”\n\n"
                        f"Context:\n{_snippet(chunk, 320)}"
                    ),
                }
            ]
        elif qtype == "LONG":
            blocks = [
                {
                    "type": "text",
                    "text": (
                        "Answer with clear introduction, body, and conclusion (use sub-headings).\n\n"
                        f"Discuss the concepts illustrated below.\n\n{_snippet(chunk, 520)}"
                    ),
                }
            ]
        else:
            blocks = [
                {
                    "type": "text",
                    "text": (
                        "Answer in 60–100 words.\n\n"
                        f"Summarise the main teaching points from this part of the chapter:\n\n{_snippet(chunk, 400)}"
                    ),
                }
            ]

        built[i] = {
            "section": item["section"],
            "section_title": item.get("section_title"),
            "section_instruction": item.get("section_instruction"),
            "marks": marks,
            "question": _blocks_to_plain(blocks),
            "blocks": blocks,
            "_instant": True,
            "_instant_mcq_correct_index": 0 if qtype == "MCQ" else None,
        }

    out = [built[j] for j in range(len(plan))]
    for i, q in enumerate(out):
        q["number"] = i + 1
    return out


def generate_answers_instant(questions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    answers = []
    for q in questions:
        n = q["number"]
        blocks = q.get("blocks") or []
        text = ""
        if q.get("_instant_mcq_correct_index") == 0:
            for b in blocks:
                if b.get("type") == "options":
                    opts = b.get("options") or []
                    if opts:
                        text = f"Correct option: (a) — {opts[0]}"
                    break
        elif any(b.get("type") == "sub_questions" for b in blocks):
            text = (
                "Model outline: (a) Two facts/processes named from Excerpt A with one line each. "
                "(b) One clear link (extra example, definition, or application) from Excerpt B vs A."
            )
        elif "contains the numeric values" in q.get("question", "").lower():
            m = re.search(
                r"values\s+([\d.]+)\s+and\s+([\d.]+)",
                q.get("question", ""),
                re.I,
            )
            if m:
                try:
                    a, b = float(m.group(1)), float(m.group(2))
                    text = f"Answer: {abs(a - b)} (working: |{a} - {b}| = {abs(a - b)})."
                except ValueError:
                    text = "Answer: compute absolute difference from the two values stated in the question."
            else:
                text = "Answer: compute absolute difference from the two values stated in the question."
        else:
            text = (
                "Model answer: Use the passage only; define terms, give 2–3 bullet points, and link cause–effect where asked."
            )
        answers.append({"number": n, "answer": text})
    return answers


def clear_chunk_cache() -> None:
    _CHUNK_CACHE.clear()
    _FILTERED_CACHE.clear()
