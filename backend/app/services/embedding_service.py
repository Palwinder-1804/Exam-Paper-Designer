import os
import pickle

import faiss
import numpy as np

from app.config import DB_PATH
from app.core.embeddings import encode_texts


def create_vector_store(chunks, batch_size: int = 128):
    os.makedirs(DB_PATH, exist_ok=True)

    index = None
    for i in range(0, len(chunks), batch_size):
        batch = chunks[i : i + batch_size]
        embeddings = encode_texts(batch, batch_size=batch_size)

        if index is None:
            index = faiss.IndexFlatL2(embeddings.shape[1])
        index.add(np.array(embeddings, dtype=np.float32))

    faiss.write_index(index, f"{DB_PATH}/index.faiss")
    with open(f"{DB_PATH}/chunks.pkl", "wb") as f:
        pickle.dump(chunks, f)

    return index, chunks
