from langchain_community.document_loaders import PyPDFLoader
import tempfile
import os
from typing import Union

def load_pdf(pdf_source: Union[bytes, str]):
    """
    Load a PDF into LangChain documents.

    pdf_source:
      - bytes: will be written to a temporary file
      - str: treated as a file path
    """
    should_cleanup = False
    if isinstance(pdf_source, (bytes, bytearray)):
        temp = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
        temp.write(pdf_source)
        temp.flush()
        pdf_path = temp.name
        should_cleanup = True
    else:
        pdf_path = pdf_source

    loader = PyPDFLoader(pdf_path)
    docs = loader.load()

    if should_cleanup:
        try:
            os.remove(pdf_path)
        except Exception:
            pass

    return docs