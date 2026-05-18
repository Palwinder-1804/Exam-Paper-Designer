"""Match syllabus figures to questions and attach them when needed."""
import json
import os
import re
from typing import Any, Dict, List, Optional, Set

FIGURES_JSON = "app/static/figures/current/figures.json"
FIG_DIR = "app/static/figures/current"


def load_figures() -> List[Dict[str, Any]]:
    if not os.path.exists(FIGURES_JSON):
        return []
    with open(FIGURES_JSON, encoding="utf-8") as f:
        data = json.load(f)
    return [x for x in data if isinstance(x, dict) and x.get("id")]


def figure_path(fig_id: str) -> Optional[str]:
    for fig in load_figures():
        if fig.get("id") == fig_id:
            fn = fig.get("filename")
            if fn:
                p = os.path.join(FIG_DIR, fn)
                if os.path.exists(p):
                    return p
    return None


class FigureAllocator:
    """Round-robin unused figures so each question can get a distinct diagram."""

    def __init__(self):
        self._figures = load_figures()
        self._used: Set[str] = set()
        self._idx = 0

    @property
    def available_ids(self) -> List[str]:
        return [f["id"] for f in self._figures if f.get("id")]

    def allocate(self, preferred_page: Optional[int] = None) -> Optional[str]:
        if not self._figures:
            return None

        if preferred_page is not None:
            for fig in self._figures:
                fid = fig.get("id")
                if fid and fig.get("page") == preferred_page and fid not in self._used:
                    self._used.add(fid)
                    return fid

        n = len(self._figures)
        for _ in range(n):
            fig = self._figures[self._idx % n]
            self._idx += 1
            fid = fig.get("id")
            if fid and fid not in self._used:
                self._used.add(fid)
                return fid

        # Reuse if exhausted
        fig = self._figures[self._idx % n]
        self._idx += 1
        return fig.get("id")

    def page_from_context(self, context: str) -> Optional[int]:
        m = re.search(r"\bpage\s*(\d+)\b", context, re.I)
        if m:
            return int(m.group(1))
        m = re.search(r"\bfig\.?\s*(\d+)", context, re.I)
        if m:
            # Heuristic: map fig number to approximate page in NCERT-style books
            return max(1, int(m.group(1)) // 2)
        return None


def attach_figure_block(
    blocks: List[Dict[str, Any]],
    fig_id: str,
    caption: str = "",
    *,
    before_subquestions: bool = True,
) -> List[Dict[str, Any]]:
    """Insert figure block; remove textual 'refer to fig' lines."""
    fig_block = {
        "type": "figure",
        "figure_id": fig_id,
        "caption": caption or None,
    }
    cleaned: List[Dict[str, Any]] = []
    for b in blocks:
        if b.get("type") == "text":
            t = b.get("text", "")
            t = re.sub(
                r"\(?\s*refer to\s+(fig\.?|figure|diagram)[^.)]*\)?",
                "",
                t,
                flags=re.I,
            ).strip()
            t = re.sub(r"\bFig\.?\s*\d+(\.\d+)?\b", "", t).strip()
            if t:
                cleaned.append({"type": "text", "text": t})
        else:
            cleaned.append(b)

    if not cleaned:
        cleaned = [{"type": "text", "text": "Study the diagram below and answer."}]

    if before_subquestions:
        insert_at = 0
        for i, b in enumerate(cleaned):
            if b.get("type") == "sub_questions":
                insert_at = i
                break
            insert_at = i + 1
        cleaned.insert(insert_at, fig_block)
    else:
        cleaned.append(fig_block)
    return cleaned


def needs_diagram(q_type: str, text: str) -> bool:
    if q_type in ("CASE_BASED",) and re.search(
        r"\b(graph|diagram|figure|chart|plot|curve|circuit|ray)\b", text, re.I
    ):
        return True
    if re.search(r"\b(graph|diagram|figure|chart|distance[- ]time|circuit)\b", text, re.I):
        return True
    return False
