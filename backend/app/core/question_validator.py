import re
from typing import Any, Dict, List, Optional, Tuple

# Placeholder / non-question patterns
_REFER_ONLY = re.compile(
    r"^\s*(refer to|see)\s+(fig\.?|figure|diagram|graph)\b",
    re.I,
)
_FIG_REF = re.compile(r"\b(fig\.?\s*\d+|figure\s+\d+|diagram\s+\d+)\b", re.I)
_SUB_PART = re.compile(r"\([a-d]\)\s*.+\?", re.I | re.DOTALL)
_QUESTION_CUE = re.compile(
    r"(\?|\b(explain|define|state|calculate|find|why|how|what|which|describe|derive|prove|compare|distinguish|list|discuss|evaluate|draw|show|write|differentiate|illustrate|briefly|give|summarize|identify|name|label)\b)",
    re.I,
)
_BANNED_PHRASES = [
    "refer to fig",
    "see figure",
    "in the context of science",
    "as shown in the passage above without",
]


def _all_text(blocks: List[Dict]) -> str:
    parts = []
    for b in blocks:
        if b.get("type") == "text":
            parts.append(b.get("text", ""))
        elif b.get("type") == "sub_questions":
            for sq in b.get("items", []):
                parts.append(sq.get("text", ""))
    return "\n".join(parts).strip()


def has_figure_block(blocks: List[Dict]) -> bool:
    return any(b.get("type") == "figure" for b in blocks)


def validate_question(
    blocks: List[Dict],
    q_type: str,
    *,
    require_figure: bool = False,
) -> Tuple[bool, str]:
    text = _all_text(blocks)
    if len(text) < 35:
        return False, "Question text too short or empty"

    lower = text.lower()
    for phrase in _BANNED_PHRASES:
        if phrase in lower and "?" not in text:
            return False, f"Placeholder phrase detected: {phrase}"

    if _REFER_ONLY.match(text) and "?" not in text:
        return False, "Only a figure reference without an actual question"

    # Text mentions a figure but no embedded figure block
    if _FIG_REF.search(text) and not has_figure_block(blocks):
        return False, "Mentions figure number in text but figure not embedded"

    if q_type == "CASE_BASED":
        sub_blocks = [b for b in blocks if b.get("type") == "sub_questions"]
        if not sub_blocks:
            return False, "Case study missing sub-questions block"
        items = sub_blocks[0].get("items", [])
        if len(items) < 2:
            return False, "Case study needs at least (a) and (b)"
        for it in items:
            if "?" not in it.get("text", "") and not _QUESTION_CUE.search(it.get("text", "")):
                return False, "Sub-question missing clear prompt"
        passage = ""
        for b in blocks:
            if b.get("type") == "text":
                passage = b.get("text", "")
                break
        if len(passage) < 60:
            return False, "Case study passage too short"
    else:
        if not _QUESTION_CUE.search(text) and not _SUB_PART.search(text):
            return False, "No clear question (missing ? or question verb)"

    if require_figure and not has_figure_block(blocks):
        return False, "Diagram required but not attached"

    # Reject definition-only paragraphs without a question (common LLM mistake)
    if q_type in ("SHORT", "LONG", "CASE_BASED") and text.count("?") == 0:
        if not re.search(
            r"\b(explain|calculate|find|why|how|what|which|describe|derive|prove)\b",
            text,
            re.I,
        ):
            return False, "Descriptive paragraph without a question prompt"

    return True, "ok"


def similarity(a: str, b: str) -> float:
    wa = set(a.lower().split())
    wb = set(b.lower().split())
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / len(wa | wb)
