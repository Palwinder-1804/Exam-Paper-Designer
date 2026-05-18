import json
import os
import re
import tempfile
from io import BytesIO
from typing import Any, Dict, List, Union

from pypdf import PdfReader
from PIL import Image

FIG_DIR = "app/static/figures/current"
FIGURES_JSON_PATH = os.path.join(FIG_DIR, "figures.json")
MAX_FIGURES = 80
MAX_PAGE_SNAPSHOTS = 25


def _guess_extension(data: bytes) -> str:
    if data.startswith(b"\xFF\xD8\xFF"):
        return "jpg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if data.startswith(b"GIF87a") or data.startswith(b"GIF89a"):
        return "gif"
    if data.startswith(b"BM"):
        return "bmp"
    return "img"


def _save_image(data: bytes, out_path: str) -> None:
    try:
        img = Image.open(BytesIO(data))
        img.save(out_path, format="PNG")
    except Exception:
        with open(out_path, "wb") as f:
            f.write(data)


def _render_page_snapshots(temp_path: str, reader: PdfReader) -> List[Dict[str, Any]]:
    """Render PDF pages that mention figures (for vector-only textbooks)."""
    snapshots: List[Dict[str, Any]] = []
    try:
        import pypdfium2 as pdfium
    except ImportError:
        return snapshots

    try:
        pdf = pdfium.PdfDocument(temp_path)
        fig_idx_offset = MAX_FIGURES
        count = 0
        for page_number in range(len(pdf)):
            if count >= MAX_PAGE_SNAPSHOTS:
                break
            page = pdf[page_number]
            text = (page.get_textpage().get_text_bounded() or "").lower()
            if not re.search(r"\b(fig\.?|figure|diagram|graph)\b", text):
                continue
            bitmap = page.render(scale=1.5)
            pil = bitmap.to_pil()
            fig_id = f"page_{page_number + 1:04d}"
            out_filename = f"{fig_id}.png"
            out_path = os.path.join(FIG_DIR, out_filename)
            pil.save(out_path, format="PNG")
            snapshots.append(
                {
                    "id": fig_id,
                    "page": page_number + 1,
                    "filename": out_filename,
                    "source": "page_snapshot",
                }
            )
            count += 1
        pdf.close()
    except Exception:
        pass
    return snapshots


def extract_figures(
    pdf_source: Union[bytes, str], *, max_figures: int = MAX_FIGURES
) -> List[Dict[str, Any]]:
    os.makedirs(FIG_DIR, exist_ok=True)

    for name in os.listdir(FIG_DIR):
        if name.endswith(".json"):
            continue
        try:
            os.remove(os.path.join(FIG_DIR, name))
        except Exception:
            pass

    should_cleanup = False
    if isinstance(pdf_source, (bytes, bytearray)):
        temp = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
        temp.write(pdf_source)
        temp.flush()
        temp_path = temp.name
        should_cleanup = True
    else:
        temp_path = pdf_source

    figures: List[Dict[str, Any]] = []
    try:
        reader = PdfReader(temp_path)
        fig_idx = 1
        for page_number, page in enumerate(reader.pages, start=1):
            if fig_idx > max_figures:
                break
            try:
                page_images = list(page.images)
            except Exception:
                page_images = []
            for image_file in page_images:
                if fig_idx > max_figures:
                    break
                data = getattr(image_file, "data", None)
                if not data:
                    continue
                fig_id = f"fig_{fig_idx:04d}"
                out_filename = f"{fig_id}.png"
                out_path = os.path.join(FIG_DIR, out_filename)
                try:
                    _save_image(data, out_path)
                except Exception:
                    ext = _guess_extension(data)
                    out_filename = f"{fig_id}.{ext}"
                    out_path = os.path.join(FIG_DIR, out_filename)
                    with open(out_path, "wb") as f:
                        f.write(data)
                figures.append(
                    {
                        "id": fig_id,
                        "page": page_number,
                        "filename": out_filename,
                        "source": "embedded",
                    }
                )
                fig_idx += 1

        # Add full-page snapshots when few embedded images (common in NCERT PDFs)
        if len(figures) < 10:
            snapshots = _render_page_snapshots(temp_path, reader)
            for snap in snapshots:
                if len(figures) >= max_figures:
                    break
                figures.append(snap)

        with open(FIGURES_JSON_PATH, "w", encoding="utf-8") as f:
            json.dump(figures, f, ensure_ascii=False, indent=2)
        return figures
    finally:
        if should_cleanup:
            try:
                os.remove(temp_path)
            except Exception:
                pass
