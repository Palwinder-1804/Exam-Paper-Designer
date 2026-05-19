# Exam Paper Designer

Generate syllabus-aligned question papers from uploaded PDF notes using **RAG** (FAISS).  
By default the API uses **instant mode** (no LLM): papers build in **seconds** on an i5 with 8GB RAM.  
Enable **Use Ollama AI** in the UI (or `use_llm: true` in the API) for higher-quality wording — that path needs Ollama and is much slower on CPU.

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

Requires [Ollama](https://ollama.com) **only if** you turn on **Use Ollama AI** in the app (or send `use_llm: true` in `POST /generate`).

**Frontend**:

```bash
streamlit run frontend/app.py
```

Set `API_BASE` if the API is not on `http://127.0.0.1:8000`.

## Instant vs AI mode (important for weak PCs)

| Mode | Speed | Needs Ollama |
|------|--------|----------------|
| **Instant** (default) | Usually **2–15 seconds** total (depends on PDF export) | No |
| **AI (`use_llm`)** | Minutes on CPU | Yes (`phi3:mini` or smaller) |

Instant mode builds questions from retrieved syllabus chunks (templates + MCQ / case study / numerical heuristics). Quality is lower than a full LLM but usable for drafts and demos.

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
