# frontend.py
import streamlit as st
import requests
import os
from app import process_pdf, process_image, process_docx, process_text, audit_text, summarize_document
from risk_score import calculate_risk

st.set_page_config(page_title="ToS Auditor", page_icon="⚖️")
st.title("⚖️ Legal ToS Auditor")

# The URL of our FastAPI backend window (run separately with:
# uvicorn app:app --reload). If it isn't running, every audit call
# below automatically falls back to running the Gemini pipeline
# in-process instead -- so the app works either way.
BACKEND_URL = "http://127.0.0.1:8000"
BACKEND_TIMEOUT_SECONDS = 5

UPLOAD_FOLDER = "temp_uploads"
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)


def display_audit_results(findings):
    if isinstance(findings, dict):
        findings = [findings]

    if not findings:
        st.success("✅ No risky or contradictory clauses detected.")
        return

    st.subheader("📋 Legal Audit Findings")
    high_risk_count, contradiction_count = 0, 0

    for f in findings:
        clause_number = f.get("clause_number", "?")
        clause_text = f.get("clause_text", "")
        risk_category = f.get("risk_category", "compliant")
        legal_citation = f.get("legal_citation", "")
        law_excerpt = f.get("law_excerpt", "")

        if risk_category in ["hidden_trap", "data_privacy_risk", "high_risk"]:
            high_risk_count += 1
            st.error(f"🚩 **High Risk — Clause #{clause_number}** — Violates: `{legal_citation}`")
            with st.expander(f"🔍 View flagged clause #{clause_number}"):
                st.markdown(f"**Flagged clause:** *\"{clause_text}\"*")
                if law_excerpt:
                    st.markdown(f"**Matched law text:** *\"{law_excerpt}\"*")

        elif risk_category in ["contradiction", "medium_risk"]:
            contradiction_count += 1
            st.warning(f"⚠️ **Possible Contradiction — Clauses #{clause_number}**")
            with st.expander(f"🔍 View flagged clauses #{clause_number}"):
                st.markdown(clause_text)

        else:
            st.success("✅ Compliant")

    st.caption(f"Summary: {high_risk_count} high-risk clause(s), {contradiction_count} contradiction(s) found.")


def display_summary(summary_text, overall_risk, risk_score, suggestion):

    st.subheader("📝 What This Document Says")

    text = (
        f"**AI Risk Score:** {risk_score}/10\n\n"
        f"**Overall Risk:** {overall_risk.capitalize()}\n\n"
        f"{summary_text}\n\n"
        f"💡 **Suggestion:** {suggestion}"
    )

    if overall_risk == "high":
        st.error(text)

    elif overall_risk == "medium":
        st.warning(text)

    else:
        st.success(text)


def display_results(matching_laws):
    """Kept for any other caller that still passes raw FAISS/law documents
    directly (e.g. ad-hoc debugging), separate from the audit flow above."""
    if not matching_laws:
        st.warning("⚠️ No relevant legal provision found for this text.")
    else:
        st.write("**Most relevant law found:**")
        st.info(matching_laws[0].page_content)


def _extract_text_locally(uploaded_file):
    """Saves an uploaded Streamlit file to disk and runs it through the
    right recipe to get plain text -- used both by the local fallback
    path and to build the multipart upload sent to the backend."""
    temp_filepath = os.path.join(UPLOAD_FOLDER, uploaded_file.name)
    with open(temp_filepath, "wb") as f:
        f.write(uploaded_file.getvalue())

    name_lower = uploaded_file.name.lower()
    if name_lower.endswith(".pdf"):
        return " ".join(c.page_content for c in process_pdf(temp_filepath))
    elif name_lower.endswith((".png", ".jpg", ".jpeg")):
        return process_image(temp_filepath)
    elif name_lower.endswith(".docx"):
        return " ".join(c.page_content for c in process_docx(temp_filepath))
    return None


def run_audit(uploaded_file=None, raw_text=None):
    """
    Runs a full audit (summary + risk/contradiction findings) for either
    an uploaded file or pasted text.

    Tries the FastAPI backend (/audit-file/ or /audit-text/) first --
    useful if you're running the backend separately, e.g. so multiple
    frontends or API clients can share one running instance of the
    Gemini pipeline. If the backend isn't reachable (ConnectionError,
    timeout, or non-200 response), transparently falls back to calling
    the same Gemini pipeline functions directly and in-process, so the
    app keeps working standalone with zero extra setup.

    Returns (summary_text, overall_risk, findings, error_message).
    error_message is None on success.
    """
    try:
        if uploaded_file is not None:
            files = {"file": (uploaded_file.name, uploaded_file.getvalue(), uploaded_file.type)}
            response = requests.post(f"{BACKEND_URL}/audit-file/", files=files, timeout=BACKEND_TIMEOUT_SECONDS)
        else:
            response = requests.post(f"{BACKEND_URL}/audit-text/", data={"raw_text": raw_text}, timeout=BACKEND_TIMEOUT_SECONDS)

        if response.status_code == 200:
            result = response.json()
            if "error" in result:
                return None, None, None, None, None, result["error"]
            st.caption("🌐 Audited via FastAPI backend.")
            summary_text = result.get("summary", "")
            findings = result.get("findings", [])

            risk_score, overall_risk, suggestion = calculate_risk(summary_text)

            return (
                summary_text,
                overall_risk,
                findings,
                risk_score,
                suggestion,
                None
            )
        else:
            raise requests.exceptions.RequestException(f"Backend returned status {response.status_code}")

    except requests.exceptions.RequestException:
        # Backend not running (or errored) -- fall back to running the
        # Gemini pipeline directly, in-process.
        st.caption("ℹ️ Backend not reachable — running the audit locally instead.")

        if uploaded_file is not None:
            text_to_audit = _extract_text_locally(uploaded_file)
            if text_to_audit is None:
                return None, None, None, None, None, "Sorry, we don't support this file type."
        else:
            text_to_audit = raw_text

        summary_text, overall_risk = summarize_document(text_to_audit)
        findings = audit_text(text_to_audit)

        risk_score, overall_risk, suggestion = calculate_risk(summary_text)

        return (
            summary_text,
            overall_risk,
            findings,
            risk_score,
            suggestion,
            None
        )


tab1, tab2 = st.tabs(["📁 Upload Document", "📝 Paste Text"])

# ==========================================
# TAB 1: UPLOAD
# ==========================================
with tab1:
    uploaded_files = st.file_uploader(
        "Upload your ToS documents (PDF, DOCX, or Images)",
        type=["pdf", "png", "jpg", "jpeg", "docx"],
        accept_multiple_files=True
    )

    if uploaded_files:
        st.success(f"Uploaded {len(uploaded_files)} file(s).")

        if st.button("Start Audit on Files"):
            for uploaded_file in uploaded_files:
                st.write(f"**Processing:** {uploaded_file.name}")

                summary_text, overall_risk, findings, risk_score, suggestion, error = run_audit( uploaded_file=uploaded_file)
                                                                                                

                if error:
                    st.error(error)
                    continue

                display_summary(summary_text, overall_risk, risk_score, suggestion)
                display_audit_results(findings)

# ==========================================
# TAB 2: PASTE TEXT
# ==========================================
with tab2:
    pasted_tos = st.text_area(
        "Paste Terms of Service here:",
        height=350,
        key="tos_input_area"
    )

    if st.button("Start Audit on Pasted Text", key="audit_paste_btn"):
        if pasted_tos.strip():
            summary_text, overall_risk, findings, risk_score, suggestion, error = run_audit(raw_text=pasted_tos)

            if error:
                st.error(error)
            else:
               display_summary(
                summary_text,
                overall_risk,
                risk_score,
                suggestion
            )
               display_audit_results(findings)
        else:
            st.warning("Please paste some text before starting the audit.")