from fastapi import APIRouter, UploadFile
from app.core.instant_generator import clear_chunk_cache
from app.services.document_service import process_document
from app.services.embedding_service import create_vector_store
from app.services.figure_extraction_service import extract_figures
from app.core import state
import tempfile
import shutil
import os
router = APIRouter()

@router.post("/upload")
def upload(file: UploadFile):
    # Avoid reading the entire PDF into memory for large uploads.
    temp = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
    temp_path = temp.name
    try:
        with temp:
            shutil.copyfileobj(file.file, temp)

        # Refresh cached vector store so generation uses the new upload.
        state.index = None
        state.chunks = None
        clear_chunk_cache()

        from concurrent.futures import ThreadPoolExecutor
        chunks = process_document(temp_path)
        
        if not chunks:
            from fastapi import HTTPException
            raise HTTPException(status_code=400, detail="No text could be extracted from the PDF. Please ensure it is a text-based PDF and not just scanned images.")

        with ThreadPoolExecutor(max_workers=2) as executor:
            future_vector = executor.submit(create_vector_store, chunks)
            future_figures = executor.submit(extract_figures, temp_path)
            future_vector.result()
            figures = future_figures.result()
    finally:
        try:
            os.remove(temp_path)
        except Exception:
            pass

    return {"message": "Stored in vector DB", "figures_extracted": len(figures)}