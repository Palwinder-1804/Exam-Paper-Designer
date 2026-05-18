"""Shared embedding model singleton — loaded once per process."""
import os
from functools import lru_cache

from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer

load_dotenv()

MODEL_NAME = "all-MiniLM-L6-v2"


@lru_cache(maxsize=1)
def get_embedding_model() -> SentenceTransformer:
    token = os.getenv("HF_TOKEN") or os.getenv("HUGGINGFACEHUB_API_TOKEN")
    if token:
        return SentenceTransformer(MODEL_NAME, token=token)
    return SentenceTransformer(MODEL_NAME)


def encode_texts(texts, batch_size: int = 64):
    model = get_embedding_model()
    return model.encode(texts, batch_size=batch_size, show_progress_bar=False)
