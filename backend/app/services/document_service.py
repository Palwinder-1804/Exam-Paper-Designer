from app.utils.file_loader import load_pdf
from app.utils.chunking import chunk_documents

def process_document(pdf_source):
    """
    pdf_source can be:
      - bytes (legacy)
      - a filesystem path to a PDF
    """
    docs = load_pdf(pdf_source)
    chunks = chunk_documents(docs)
    return chunks