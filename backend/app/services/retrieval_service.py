import pickle

import faiss
import numpy as np

from app.config import DB_PATH
from app.core import state
from app.core.embeddings import encode_texts


def load_vector_store():
    index = faiss.read_index(f"{DB_PATH}/index.faiss")
    with open(f"{DB_PATH}/chunks.pkl", "rb") as f:
        chunks = pickle.load(f)
    return index, chunks


def retrieve(query, k: int = 5):
    if state.index is None or state.chunks is None:
        state.index, state.chunks = load_vector_store()

    query_embedding = encode_texts([query])
    _, indices = state.index.search(np.array(query_embedding, dtype=np.float32), k)
    return [state.chunks[i] for i in indices[0] if i >= 0]
