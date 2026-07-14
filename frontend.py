# frontend.py
import os

import requests
import streamlit as st

from app import process_pdf, process_image, process_docx, audit_text, summarize_document
from risk_score import calculate_risk

# ==========================================
# PAGE CONFIG + GLOBAL STYLES
# ==========================================
st.set_page_config(
    page_title="ToS Auditor",
    page_icon="⚖️",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
        /* --- Layout width --- */
        .block-container { padding-top: 2rem; max-width: 1100px; }

        /* --- Hero header --- */
        .hero {
            background: linear-gradient(135deg, #1e3a8a 0%, #6d28d9 100%);
            padding: 2rem 2.5rem;
            border-radius: 18px;
            color: #ffffff;
            margin-bottom: 1.5rem;
            box-shadow: 0 10px 30px rgba(76, 29, 149, 0.25);
        }
        .hero h1 { color: #ffffff; margin: 0; font-size: 2.1rem; }
        .hero p  { color: #e0e7ff; margin: 0.4rem 0 0; font-size: 1.05rem; }

        /* --- Score card --- */
        .score-card {
            border-radius: 16px;
            padding: 1.2rem 1.4rem;
            text-align: center;
            color: #ffffff;
            box-shadow: 0 6px 18px rgba(0,0,0,0.12);
        }
        .score-card h2 { color:#ffffff; margin:0; font-size:2.6rem; line-height:1; }
        .score-card span { font-size:0.85rem; opacity:0.9; letter-spacing:0.5px; text-transform:uppercase; }

        .risk-high   { background: linear-gradient(135deg,#dc2626,#991b1b); }
        .risk-medium { background: linear-gradient(135deg,#f59e0b,#b45309); }
        .risk-low    { background: linear-gradient(135deg,#16a34a,#15803d); }

        /* --- Finding cards --- */
        .finding {
            border-radius: 12px;
            padding: 1rem 1.2rem;
            margin-bottom: 0.6rem;
            border-left: 6px solid;
        }
        .finding-high  { border-color:#dc2626; background:#fef2f2; }
        .finding-warn  { border-color:#f59e0b; background:#fffbeb; }
        .finding-title { font-weight:700; font-size:1.02rem; margin-bottom:0.3rem; color:#1e293b; }
        .finding-meta  { font-size:0.82rem; color:#64748b; }
        .quote {
            font-style: italic;
            color: #334155;
            border-left: 3px solid #cbd5e1;
            padding-left: 0.8rem;
            margin: 0.4rem 0;
        }
    </style>
    """,
    unsafe_allow_html=True,
)

# ==========================================
# CONFIG
# ==========================================
# The URL of our FastAPI backend (run separately with
# `uvicorn app:app --reload`). If it isn't running, every audit call
# below automatically falls back to running the Gemini pipeline
# in-process instead -- so the app works either way.
BACKEND_URL = "http://127.0.0.1:8000"
BACKEND_TIMEOUT_SECONDS = 5

UPLOAD_FOLDER = "temp_uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

RISK_META = {
    "high": ("risk-high", "🔴", "High Risk"),
    "medium": ("risk-medium", "🟠", "Medium Risk"),
    "low": ("risk-low", "🟢", "Low Risk"),
}


# ==========================================
# HERO + SIDEBAR
# ==========================================
st.markdown(
    """
    <div class="hero">
        <h1>⚖️ Legal ToS Auditor</h1>
        <p>Your AI legal detective — it reads long Terms of Service agreements and flags
        sneaky, unfair, or contradictory clauses so you don't have to.</p>
    </div>
    """,
    unsafe_allow_html=True,
)

with st.sidebar:
    st.header("ℹ️ How it works")
    st.markdown(
        """
        1. **Upload** a ToS file or **paste** the text.
        2. The AI splits it into clauses and scans each one.
        3. **RAG** matches risky clauses to real legal provisions.
        4. You get a **risk score**, a plain-language summary, and
           highlighted problem clauses.
        """
    )
    st.divider()
    st.subheader("📄 Supported files")
    st.markdown("- PDF (`.pdf`)\n- Word (`.docx`)\n- Images (`.png`, `.jpg`, `.jpeg`)")
    st.divider()
    st.caption("Powered by RAG + Gemini · This is an assistive tool, not legal advice.")


# ==========================================
# DISPLAY HELPERS
# ==========================================
def display_summary(summary_text, overall_risk, risk_score, suggestion):
    """Renders the top-level summary: score card + plain-language overview."""
    css_class, emoji, label = RISK_META.get(overall_risk, RISK_META["medium"])

    st.subheader("📝 Executive Summary")
    col_score, col_text = st.columns([1, 3], gap="large")

    with col_score:
        st.markdown(
            f"""
            <div class="score-card {css_class}">
                <span>AI Risk Score</span>
                <h2>{risk_score}<small style="font-size:1.1rem;">/10</small></h2>
                <span>{emoji} {label}</span>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.progress(min(int(risk_score * 10), 100))

    with col_text:
        st.write(summary_text)
        st.info(f"💡 **Suggestion:** {suggestion}")


def display_audit_results(findings):
    if isinstance(findings, dict):
        findings = [findings]

    if not findings:
        st.success("✅ No risky or contradictory clauses detected.")
        return

    high_risk_count = sum(
        1 for f in findings
        if f.get("risk_category") in ("hidden_trap", "data_privacy_risk", "high_risk")
    )
    contradiction_count = sum(
        1 for f in findings
        if f.get("risk_category") in ("contradiction", "medium_risk")
    )

    st.subheader("📋 Detailed Findings")
    m1, m2, m3 = st.columns(3)
    m1.metric("Total findings", len(findings))
    m2.metric("🚩 High risk", high_risk_count)
    m3.metric("⚠️ Contradictions", contradiction_count)

    for f in findings:
        clause_number = f.get("clause_number", "?")
        clause_text = f.get("clause_text", "")
        risk_category = f.get("risk_category", "compliant")
        explanation = f.get("explanation", "")
        legal_citation = f.get("legal_citation", "")
        law_excerpt = f.get("law_excerpt", "")

        if risk_category in ("hidden_trap", "data_privacy_risk", "high_risk"):
            st.markdown(
                f"""
                <div class="finding finding-high">
                    <div class="finding-title">🚩 High Risk — Clause #{clause_number}</div>
                    <div class="finding-meta">Violates: {legal_citation}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            with st.expander(f"🔍 View flagged clause #{clause_number}"):
                st.markdown(f'<div class="quote">“{clause_text}”</div>', unsafe_allow_html=True)
                if explanation:
                    st.markdown(f"**Why it's risky:** {explanation}")
                if law_excerpt:
                    st.markdown(f"**Matched law text:** *“{law_excerpt}”*")

        elif risk_category in ("contradiction", "medium_risk"):
            st.markdown(
                f"""
                <div class="finding finding-warn">
                    <div class="finding-title">⚠️ Possible Contradiction — Clauses #{clause_number}</div>
                    <div class="finding-meta">{legal_citation or "Internal inconsistency"}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            with st.expander(f"🔍 View conflicting clauses #{clause_number}"):
                st.markdown(clause_text)
                if explanation:
                    st.markdown(f"**Why it conflicts:** {explanation}")


# ==========================================
# AUDIT PIPELINE (backend-first, local fallback)
# ==========================================
def _extract_text_locally(uploaded_file):
    """Saves an uploaded Streamlit file to disk and runs it through the
    right recipe to get plain text -- used by the local fallback path."""
    safe_name = os.path.basename(uploaded_file.name)  # prevent path traversal
    temp_filepath = os.path.join(UPLOAD_FOLDER, safe_name)
    try:
        with open(temp_filepath, "wb") as f:
            f.write(uploaded_file.getvalue())

        name_lower = safe_name.lower()
        if name_lower.endswith(".pdf"):
            return " ".join(c.page_content for c in process_pdf(temp_filepath))
        elif name_lower.endswith((".png", ".jpg", ".jpeg")):
            return process_image(temp_filepath)
        elif name_lower.endswith(".docx"):
            return " ".join(c.page_content for c in process_docx(temp_filepath))
        return None
    finally:
        if os.path.exists(temp_filepath):
            os.remove(temp_filepath)


def run_audit(uploaded_file=None, raw_text=None):
    """
    Runs a full audit (summary + risk/contradiction findings) for either
    an uploaded file or pasted text.

    Tries the FastAPI backend (/audit-file/ or /audit-text/) first, and
    transparently falls back to running the same Gemini pipeline
    in-process if the backend isn't reachable.

    Returns (summary_text, overall_risk, findings, risk_score, suggestion,
    error_message). error_message is None on success.
    """
    try:
        if uploaded_file is not None:
            files = {"file": (uploaded_file.name, uploaded_file.getvalue(), uploaded_file.type)}
            response = requests.post(
                f"{BACKEND_URL}/audit-file/", files=files, timeout=BACKEND_TIMEOUT_SECONDS
            )
        else:
            response = requests.post(
                f"{BACKEND_URL}/audit-text/",
                data={"raw_text": raw_text},
                timeout=BACKEND_TIMEOUT_SECONDS,
            )

        # Try to parse backend response even on non-200 so we can surface
        # helpful error messages (e.g. OCR/Tesseract missing) instead of
        # silently falling back to local processing.
        try:
            result = response.json()
        except Exception:
            result = None

        if response.status_code != 200:
            if result and isinstance(result, dict) and "error" in result:
                return None, None, None, None, None, result["error"]
            raise requests.exceptions.RequestException(
                f"Backend returned status {response.status_code}"
            )

        if result and "error" in result:
            return None, None, None, None, None, result["error"]

        st.caption("🌐 Audited via FastAPI backend.")
        summary_text = result.get("summary", "")
        findings = result.get("findings", [])
        risk_score, overall_risk, suggestion = calculate_risk(summary_text)
        return summary_text, overall_risk, findings, risk_score, suggestion, None

    except requests.exceptions.RequestException:
        # Backend not running (or errored) -- fall back to the in-process pipeline.
        st.caption("ℹ️ Backend not reachable — running the audit locally instead.")

        try:
            if uploaded_file is not None:
                text_to_audit = _extract_text_locally(uploaded_file)
                if text_to_audit is None:
                    return None, None, None, None, None, "Sorry, we don't support this file type."
            else:
                text_to_audit = raw_text

            summary_text, overall_risk = summarize_document(text_to_audit)
            findings = audit_text(text_to_audit)
            risk_score, overall_risk, suggestion = calculate_risk(summary_text)

            return summary_text, overall_risk, findings, risk_score, suggestion, None
        except Exception as e:
            # Surface a friendly error message to the UI instead of a traceback.
            return None, None, None, None, None, str(e)


# ==========================================
# MAIN TABS
# ==========================================
tab1, tab2 = st.tabs(["📁 Upload Document", "📝 Paste Text"])

# --- TAB 1: UPLOAD ---
with tab1:
    uploaded_files = st.file_uploader(
        "Upload your ToS documents",
        type=["pdf", "png", "jpg", "jpeg", "docx"],
        accept_multiple_files=True,
        help="PDF, DOCX, or image files are supported.",
    )

    if uploaded_files:
        st.success(f"Uploaded {len(uploaded_files)} file(s).")

        if st.button("🚀 Start Audit on Files", type="primary", use_container_width=True):
            for uploaded_file in uploaded_files:
                st.divider()
                st.markdown(f"### 📄 {uploaded_file.name}")

                with st.spinner(f"Auditing {uploaded_file.name}…"):
                    summary_text, overall_risk, findings, risk_score, suggestion, error = run_audit(
                        uploaded_file=uploaded_file
                    )

                if error:
                    st.error(error)
                    continue

                display_summary(summary_text, overall_risk, risk_score, suggestion)
                display_audit_results(findings)

# --- TAB 2: PASTE TEXT ---
with tab2:
    pasted_tos = st.text_area(
        "Paste Terms of Service here:",
        height=350,
        key="tos_input_area",
        placeholder="Paste the full Terms of Service text you want to audit…",
    )

    if st.button("🚀 Start Audit on Pasted Text", key="audit_paste_btn", type="primary", use_container_width=True):
        if pasted_tos.strip():
            with st.spinner("Auditing pasted text…"):
                summary_text, overall_risk, findings, risk_score, suggestion, error = run_audit(
                    raw_text=pasted_tos
                )

            if error:
                st.error(error)
            else:
                display_summary(summary_text, overall_risk, risk_score, suggestion)
                display_audit_results(findings)
        else:
            st.warning("Please paste some text before starting the audit.")