from langchain_text_splitters import RecursiveCharacterTextSplitter

def chunk_documents(docs, *, max_chunks: int = 2000):
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=500,
        chunk_overlap=50
    )

    # Performance: do not split the full doc set and then slice.
    # For large PDFs (1000+ pages) this avoids generating huge intermediate lists.
    chunks = []
    for doc in docs:
        page_text = getattr(doc, "page_content", "")
        if not page_text:
            continue
        page_chunks = splitter.split_text(page_text)
        for c in page_chunks:
            c = (c or "").strip()
            if c:
                chunks.append(c)
                if len(chunks) >= max_chunks:
                    return chunks[:max_chunks]

    return chunks