import os

# LLM
HF_MODEL = os.getenv("HF_MODEL", "Qwen/Qwen2.5-7B-Instruct")
MAX_PARALLEL_LLM = int(os.getenv("MAX_PARALLEL_LLM", "4"))

# Generation speed vs quality
MAX_RETRIES = int(os.getenv("MAX_RETRIES", "2"))
CONTEXT_MAX_CHARS = int(os.getenv("CONTEXT_MAX_CHARS", "2200"))
QUESTION_BATCH_SIZE = int(os.getenv("QUESTION_BATCH_SIZE", "3"))  # questions per LLM call
PARALLEL_QUESTIONS = os.getenv("PARALLEL_QUESTIONS", "true").lower() in ("1", "true", "yes")
RETRIEVAL_K = int(os.getenv("RETRIEVAL_K", "3"))

# Defaults
DEFAULT_MAX_QUESTIONS = int(os.getenv("DEFAULT_MAX_QUESTIONS", "20"))
GENERATE_ANSWERS_DEFAULT = os.getenv("GENERATE_ANSWERS", "true").lower() in ("1", "true", "yes")
ANSWER_BATCH_SIZE = int(os.getenv("ANSWER_BATCH_SIZE", "10"))  # answers per LLM call

OUTPUT_DIR = "app/static/outputs"
FIGURES_DIR = "app/static/figures/current"
DB_PATH = "app/db/faiss_index"
