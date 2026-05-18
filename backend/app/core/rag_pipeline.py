from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from sentence_transformers import SentenceTransformer
import faiss
import numpy as np
import tempfile
import os
from dotenv import load_dotenv

load_dotenv()

HF_TOKEN = os.getenv("HF_TOKEN") or os.getenv("HUGGINGFACEHUB_API_TOKEN")
if HF_TOKEN:
    model = SentenceTransformer("all-MiniLM-L6-v2", token=HF_TOKEN)
else:
    model = SentenceTransformer("all-MiniLM-L6-v2")

def query_rag(chunks, query):
    results = retrieve(chunks, query)
    return "\n".join(results)

def process_document(file):
    temp = tempfile.NamedTemporaryFile(delete=False)
    temp.write(file.file.read())

    loader = PyPDFLoader(temp.name)
    docs = loader.load()

    splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50)
    chunks = splitter.split_documents(docs)

    return [chunk.page_content for chunk in chunks]


def embed_chunks(chunks):
    return model.encode(chunks)


def retrieve(chunks, query, k=3):
    embeddings = embed_chunks(chunks)
    index = faiss.IndexFlatL2(embeddings.shape[1])
    index.add(np.array(embeddings))

    q_emb = model.encode([query])
    _, indices = index.search(np.array(q_emb), k)

    return [chunks[i] for i in indices[0]]