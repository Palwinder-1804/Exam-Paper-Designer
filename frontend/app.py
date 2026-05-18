import os

import requests
import streamlit as st

API_BASE = os.getenv("API_BASE", "http://127.0.0.1:8000")

st.set_page_config(
    page_title="Exam Paper Designer",
    page_icon="📋",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
<style>
    @import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&display=swap');
    html, body, [class*="css"] { font-family: 'DM Sans', sans-serif; }
    .main-header {
        background: linear-gradient(135deg, #1e3a5f 0%, #2d5a87 50%, #3d7ab5 100%);
        padding: 2rem 2.5rem;
        border-radius: 16px;
        color: white;
        margin-bottom: 1.5rem;
        box-shadow: 0 8px 32px rgba(30, 58, 95, 0.25);
    }
    .main-header h1 { margin: 0; font-size: 2rem; font-weight: 700; }
    .main-header p { margin: 0.5rem 0 0; opacity: 0.9; font-size: 1rem; }
    .template-card {
        background: #f8fafc;
        border: 1px solid #e2e8f0;
        border-radius: 12px;
        padding: 1rem 1.25rem;
        margin-top: 0.5rem;
    }
    .status-ok { color: #059669; font-weight: 600; }
    .status-warn { color: #d97706; font-weight: 600; }
</style>
""",
    unsafe_allow_html=True,
)


@st.cache_data(ttl=60)
def fetch_templates():
    try:
        r = requests.get(f"{API_BASE}/templates", timeout=10)
        if r.status_code == 200:
            return r.json().get("templates", [])
    except requests.RequestException:
        pass
    return []


def download_url(path: str) -> str:
    name = os.path.basename(path.replace("\\", "/"))
    return f"{API_BASE}/download/{name}"


st.markdown(
    """
<div class="main-header">
    <h1>📋 Exam Paper Designer</h1>
    <p>Upload your syllabus PDF → pick an exam template → generate a print-ready question paper with answer key</p>
</motion>
""".replace("</motion>", "</div>"),
    unsafe_allow_html=True,
)

with st.sidebar:
    st.header("⚙️ Paper settings")
    institution = st.text_input("Institution name", "ABC Senior Secondary School")
    subject = st.text_input("Subject", "Science / Mathematics")
    exam_date = st.text_input("Exam date line", "Date: _______________")
    difficulty = st.selectbox("Difficulty", ["easy", "medium", "hard"], index=1)
    full_paper = st.checkbox(
        "Full paper (all sections, slower)",
        value=False,
        help="Unchecked: scales question count for faster generation while keeping section structure.",
    )
    max_q = st.slider("Max questions (quick mode)", 8, 40, 15, disabled=full_paper)
    include_answers = st.checkbox(
        "Generate answer key",
        value=False,
        help="Skip for fastest run — answers roughly double generation time.",
    )
    export_docx = st.checkbox("Export DOCX", value=True)
    st.divider()
    st.caption(f"API: `{API_BASE}`")

col_upload, col_templates = st.columns([1, 1.2])

with col_upload:
    st.subheader("1️⃣ Upload syllabus")
    file = st.file_uploader("PDF syllabus / notes", type=["pdf"])

    if st.button("Process PDF", type="primary", use_container_width=True):
        if not file:
            st.error("Please select a PDF file first.")
        else:
            with st.spinner("Extracting text, building vector index & figures…"):
                try:
                    res = requests.post(
                        f"{API_BASE}/upload",
                        files={"file": (file.name, file.getvalue(), "application/pdf")},
                        timeout=600,
                    )
                    if res.status_code == 200:
                        data = res.json()
                        st.session_state["uploaded"] = True
                        st.success(
                            f"Ready — {data.get('figures_extracted', 0)} figures indexed."
                        )
                    else:
                        detail = res.json().get("detail", res.text) if res.text else "Upload failed"
                        st.error(detail)
                except requests.RequestException as e:
                    st.error(f"Cannot reach backend: {e}")

    if st.session_state.get("uploaded"):
        st.markdown('<p class="status-ok">✓ Syllabus indexed</p>', unsafe_allow_html=True)
    else:
        st.markdown('<p class="status-warn">○ Upload required before generate</p>', unsafe_allow_html=True)

with col_templates:
    st.subheader("2️⃣ Choose exam template")
    templates = fetch_templates()
    template_id = "cbse"

    if not templates:
        st.warning(
            "Backend offline. Start: `cd backend && uvicorn app.main:app --reload`"
        )
        template_id = st.selectbox(
            "Template (fallback)",
            ["cbse", "mid_term", "university", "jee", "gate", "neet", "upsc", "competitive"],
        )
    else:
        labels = {
            t["id"]: f"{t['name']} — {t['duration']} | {t['maximum_marks']} marks"
            for t in templates
        }
        template_id = st.selectbox(
            "Template",
            options=[t["id"] for t in templates],
            format_func=lambda x: labels.get(x, x),
        )
        selected = next((t for t in templates if t["id"] == template_id), None)
        if selected:
            st.markdown(
                f'<div class="template-card"><strong>{selected["name"]}</strong><br/>'
                f'<small>{selected.get("description", "")}</small><br/>'
                f'<small>Sections: {selected["sections_count"]} · '
                f'Types: {", ".join(selected.get("question_types", []))}</small></div>',
                unsafe_allow_html=True,
            )

st.divider()
st.subheader("3️⃣ Generate question paper")

if st.button("Generate exam paper", type="primary", use_container_width=True):
    if not st.session_state.get("uploaded"):
        st.warning("Upload and process a PDF first.")
    else:
        payload = {
            "template": template_id,
            "difficulty": difficulty,
            "institution": institution,
            "subject": subject,
            "exam_date": exam_date,
            "full_paper": full_paper,
            "max_questions": None if full_paper else max_q,
            "include_answers": include_answers,
            "export_docx": export_docx,
        }
        with st.spinner("Generating questions in parallel (may take a few minutes)…"):
            try:
                res = requests.post(f"{API_BASE}/generate", json=payload, timeout=3600)
                if res.status_code != 200:
                    detail = res.json().get("detail", res.text) if res.text else "Generation failed"
                    st.error(detail)
                else:
                    data = res.json()
                    st.session_state["result"] = data
                    meta = data.get("meta", {})
                    n = meta.get("questions_generated", "?")
                    timing = meta.get("timing_seconds", {})
                    st.success(
                        f"Generated {n} questions in {timing.get('total', '?')}s "
                        f"(questions: {timing.get('questions', '?')}s"
                        + (
                            f", answers: {timing.get('answers', '?')}s"
                            if meta.get("include_answers")
                            else ""
                        )
                        + ")"
                    )
            except requests.RequestException as e:
                st.error(f"Request failed: {e}")

result = st.session_state.get("result")
if result:
    tab_paper, tab_answers, tab_download = st.tabs(["Question paper", "Answer key", "Downloads"])

    with tab_paper:
        st.text_area("Preview", result.get("paper", ""), height=420, label_visibility="collapsed")

    with tab_answers:
        st.text_area("Answer key", result.get("answers", ""), height=420, label_visibility="collapsed")

    with tab_download:
        c1, c2, c3 = st.columns(3)
        for col, key, label in [
            (c1, "pdf", "📄 Question paper (PDF)"),
            (c2, "docx", "📝 Question paper (DOCX)"),
            (c3, "answer_pdf", "✅ Answer key (PDF)"),
        ]:
            path = result.get(key, "")
            if path:
                url = download_url(path)
                try:
                    r = requests.get(url, timeout=60)
                    if r.status_code == 200:
                        fname = os.path.basename(path.replace("\\", "/"))
                        col.download_button(
                            label,
                            data=r.content,
                            file_name=fname,
                            use_container_width=True,
                        )
                except requests.RequestException:
                    col.link_button(label, url)
