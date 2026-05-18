# Exam Paper Designer

Generate syllabus-aligned question papers from uploaded PDF notes using RAG + local LLM (Ollama).

## Templates (8 types)

| ID | Exam style |
|----|------------|
| `cbse` | CBSE Class 12 board pattern |
| `mid_term` | Compact mid-term class test |
| `university` | University end-semester (Parts A/B/C) |
| `jee` | JEE Main Paper 1 |
| `neet` | NEET UG |
| `gate` | GATE |
| `upsc` | UPSC Prelims GS |
| `competitive` | SSC / Banking style |

Quick mode scales to ~20 questions; enable **Full paper** in the UI for complete section counts.

## Run

**Backend** (from `backend/`):

```bash
cd backend
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Requires [Ollama](https://ollama.com) with `phi3:mini` (or set `OLLAMA_MODEL`).

**Frontend**:

```bash
streamlit run frontend/app.py
```

Set `API_BASE` if the API is not on `http://127.0.0.1:8000`.

## Speed tips

| Setting | Effect |
|---------|--------|
| Uncheck **Generate answer key** | ~40–50% faster |
| **mid_term** template + 12 questions | Fastest useful run |
| `OLLAMA_MODEL=llama3.2:1b` | Smaller/faster local model |
| `QUESTION_BATCH_SIZE=5` | More questions per LLM call |
| `MAX_PARALLEL_LLM=6` | More parallel batches (if CPU/GPU allows) |
| `PARALLEL_QUESTIONS=false` | Slower but slightly more consistent |

Env vars (optional, in `.env`):

```
OLLAMA_MODEL=phi3:mini
MAX_PARALLEL_LLM=4
QUESTION_BATCH_SIZE=3
CONTEXT_MAX_CHARS=2200
MAX_RETRIES=2
```
