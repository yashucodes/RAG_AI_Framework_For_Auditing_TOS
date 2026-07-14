# frontend.py
import os
from datetime import datetime

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
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

        html, body, [class*="css"] { font-family: 'Inter', sans-serif; }

        /* --- Layout width --- */
        .block-container { padding-top: 1.6rem; max-width: 1120px; }

        /* --- Hero header --- */
        .hero {
            background: linear-gradient(135deg, #4338ca 0%, #7c3aed 55%, #a855f7 100%);
            padding: 2.2rem 2.6rem;
            border-radius: 22px;
            color: #ffffff;
            margin-bottom: 1.4rem;
            box-shadow: 0 18px 40px rgba(124, 58, 237, 0.28);
            position: relative;
            overflow: hidden;
        }
        .hero::after {
            content: "";
            position: absolute;
            right: -60px; top: -60px;
            width: 220px; height: 220px;
            background: radial-gradient(circle, rgba(255,255,255,0.18), transparent 70%);
            border-radius: 50%;
        }
        .hero h1 { color: #ffffff; margin: 0; font-size: 2.2rem; font-weight: 800; letter-spacing: -0.5px; }
        .hero p  { color: #ede9fe; margin: 0.5rem 0 0; font-size: 1.06rem; max-width: 640px; }

        /* --- Feature cards (landing) --- */
        .feat {
            background: #ffffff;
            border: 1px solid #ece9fb;
            border-radius: 16px;
            padding: 1.2rem 1.3rem;
            height: 100%;
            box-shadow: 0 4px 14px rgba(76,29,149,0.06);
            transition: transform .15s ease, box-shadow .15s ease;
        }
        .feat:hover { transform: translateY(-3px); box-shadow: 0 12px 26px rgba(76,29,149,0.12); }
        .feat .ico { font-size: 1.7rem; }
        .feat h4 { margin: 0.5rem 0 0.25rem; font-size: 1.05rem; color:#1e293b; }
        .feat p  { margin: 0; font-size: 0.9rem; color:#64748b; }

        /* --- Risk gauge (conic donut) --- */
        .gauge-wrap { display:flex; flex-direction:column; align-items:center; }
        .gauge {
            width: 168px; height: 168px; border-radius: 50%;
            display: flex; align-items: center; justify-content: center;
            box-shadow: 0 8px 22px rgba(0,0,0,0.10);
        }
        .gauge-inner {
            width: 128px; height: 128px; border-radius: 50%;
            background: #ffffff;
            display: flex; flex-direction: column;
            align-items: center; justify-content: center;
        }
        .gauge-inner .num { font-size: 2.6rem; font-weight: 800; line-height: 1; color:#1e293b; }
        .gauge-inner .num small { font-size: 1rem; color:#94a3b8; font-weight:600; }
        .pill {
            display:inline-block; margin-top:0.7rem;
            padding: 0.28rem 0.9rem; border-radius: 999px;
            font-size: 0.82rem; font-weight: 700; letter-spacing:0.3px;
            color:#ffffff;
        }
        .pill-high   { background:#dc2626; }
        .pill-medium { background:#f59e0b; }
        .pill-low    { background:#16a34a; }

        /* --- Finding cards --- */
        .finding {
            border-radius: 14px;
            padding: 1rem 1.2rem;
            margin-bottom: 0.7rem;
            border-left: 6px solid;
            box-shadow: 0 2px 10px rgba(15,23,42,0.05);
        }
        .finding-high  { border-color:#dc2626; background:#fef2f2; }
        .finding-warn  { border-color:#f59e0b; background:#fffbeb; }
        .finding-head  { display:flex; align-items:center; gap:0.5rem; flex-wrap:wrap; }
        .finding-title { font-weight:700; font-size:1.02rem; color:#1e293b; }
        .chip {
            font-size:0.72rem; font-weight:700; padding:0.15rem 0.6rem;
            border-radius:999px; color:#fff; text-transform:uppercase; letter-spacing:0.4px;
        }
        .chip-high { background:#dc2626; }
        .chip-warn { background:#f59e0b; }
        .finding-meta  { font-size:0.82rem; color:#64748b; margin-top:0.3rem; }
        .quote {
            font-style: italic;
            color: #334155;
            border-left: 3px solid #cbd5e1;
            padding-left: 0.8rem;
            margin: 0.4rem 0;
        }

        /* --- Backend status badge --- */
        .status { display:flex; align-items:center; gap:0.5rem; font-size:0.88rem; font-weight:600; }
        .dot { width:10px; height:10px; border-radius:50%; display:inline-block; }
        .dot-on  { background:#16a34a; box-shadow:0 0 0 4px rgba(22,163,74,0.15); }
        .dot-off { background:#94a3b8; box-shadow:0 0 0 4px rgba(148,163,184,0.15); }

        /* Buttons */
        .stButton>button { border-radius: 12px; font-weight:600; }
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
# Short timeout just to check if the backend is alive.
HEALTHCHECK_TIMEOUT_SECONDS = 2
# Generous timeout for the actual audit -- the Gemini pipeline is slow,
# so this must be large or the request would time out mid-audit and be
# mistaken for the backend being down.
AUDIT_TIMEOUT_SECONDS = 600

UPLOAD_FOLDER = "temp_uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

RISK_META = {
    "high": ("#dc2626", "🔴", "High Risk", "pill-high"),
    "medium": ("#f59e0b", "🟠", "Medium Risk", "pill-medium"),
    "low": ("#16a34a", "🟢", "Low Risk", "pill-low"),
}

if "results" not in st.session_state:
    st.session_state.results = []


# ==========================================
# BACKEND STATUS
# ==========================================
@st.cache_data(ttl=8, show_spinner=False)
def backend_is_up():
    """Fast health check against the backend root endpoint. Cached briefly
    so we don't ping on every rerun."""
    try:
        r = requests.get(f"{BACKEND_URL}/", timeout=HEALTHCHECK_TIMEOUT_SECONDS)
        return r.status_code == 200
    except requests.exceptions.RequestException:
        return False


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
    st.subheader("🔌 Engine status")
    online = backend_is_up()
    if online:
        st.markdown(
            '<div class="status"><span class="dot dot-on"></span> FastAPI backend online</div>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            '<div class="status"><span class="dot dot-off"></span> Running in local mode</div>',
            unsafe_allow_html=True,
        )
        st.caption("Start the backend with `uvicorn app:app --reload` for shared/API use.")

    st.divider()
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
    if st.session_state.results:
        if st.button("🗑️ Clear results", use_container_width=True):
            st.session_state.results = []
            st.rerun()
    st.caption("Powered by RAG + Gemini · This is an assistive tool, not legal advice.")


# ==========================================
# DISPLAY HELPERS
# ==========================================
def display_summary(summary_text, overall_risk, risk_score, suggestion):
    """Renders the top-level summary: donut risk gauge + plain-language overview."""
    color, emoji, label, pill_class = RISK_META.get(overall_risk, RISK_META["medium"])
    pct = max(0, min(int(round(risk_score * 10)), 100))

    st.subheader("📝 Executive Summary")
    col_score, col_text = st.columns([1, 2.4], gap="large")

    with col_score:
        st.markdown(
            f"""
            <div class="gauge-wrap">
                <div class="gauge" style="background: conic-gradient({color} {pct}%, #e5e7eb 0);">
                    <div class="gauge-inner">
                        <span class="num">{risk_score}<small>/10</small></span>
                    </div>
                </div>
                <span class="pill {pill_class}">{emoji} {label}</span>
            </div>
            """,
            unsafe_allow_html=True,
        )

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
                    <div class="finding-head">
                        <span class="chip chip-high">High Risk</span>
                        <span class="finding-title">Clause #{clause_number}</span>
                    </div>
                    <div class="finding-meta">⚖️ Violates: {legal_citation}</div>
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
                    <div class="finding-head">
                        <span class="chip chip-warn">Contradiction</span>
                        <span class="finding-title">Clauses #{clause_number}</span>
                    </div>
                    <div class="finding-meta">{legal_citation or "Internal inconsistency"}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            with st.expander(f"🔍 View conflicting clauses #{clause_number}"):
                st.markdown(clause_text)
                if explanation:
                    st.markdown(f"**Why it conflicts:** {explanation}")


def build_report(result):
    """Builds a plain-text audit report for download."""
    lines = [
        "=" * 60,
        "  LEGAL ToS AUDITOR — AUDIT REPORT",
        "=" * 60,
        f"Source     : {result['name']}",
        f"Generated  : {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"Risk score : {result['risk_score']}/10 ({result['overall_risk'].upper()})",
        "",
        "SUMMARY",
        "-" * 60,
        result["summary"],
        "",
        f"SUGGESTION: {result['suggestion']}",
        "",
        "FINDINGS",
        "-" * 60,
    ]
    findings = result["findings"] or []
    if not findings:
        lines.append("No risky or contradictory clauses detected.")
    for i, f in enumerate(findings, 1):
        lines.append(f"{i}. [{f.get('risk_category', 'n/a')}] Clause #{f.get('clause_number', '?')}")
        if f.get("legal_citation"):
            lines.append(f"   Citation: {f['legal_citation']}")
        if f.get("explanation"):
            lines.append(f"   Note: {f['explanation']}")
        lines.append(f"   Text: {f.get('clause_text', '').strip()}")
        lines.append("")
    return "\n".join(lines)


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


def _audit_via_backend(uploaded_file, raw_text):
    """POSTs to the FastAPI backend with a long timeout. Returns the parsed
    result dict, or raises requests.exceptions.RequestException on failure."""
    if uploaded_file is not None:
        files = {"file": (uploaded_file.name, uploaded_file.getvalue(), uploaded_file.type)}
        response = requests.post(
            f"{BACKEND_URL}/audit-file/", files=files, timeout=AUDIT_TIMEOUT_SECONDS
        )
    else:
        response = requests.post(
            f"{BACKEND_URL}/audit-text/",
            data={"raw_text": raw_text},
            timeout=AUDIT_TIMEOUT_SECONDS,
        )
    if response.status_code != 200:
        raise requests.exceptions.RequestException(
            f"Backend returned status {response.status_code}"
        )
    return response.json()


def run_audit(uploaded_file=None, raw_text=None):
    """
    Runs a full audit (summary + risk/contradiction findings) for either
    an uploaded file or pasted text.

    First does a fast health check on the backend. If it's up, the audit
    runs there with a long timeout (the Gemini pipeline is slow). If the
    backend is down -- or errors mid-request -- it transparently falls
    back to the same pipeline in-process.

    Returns a dict with keys: summary, overall_risk, findings, risk_score,
    suggestion, source ("backend" | "local"), error (None on success).
    """
    def _fail(msg):
        return {"error": msg}

    use_backend = backend_is_up()

    if use_backend:
        try:
            result = _audit_via_backend(uploaded_file, raw_text)
            if "error" in result:
                return _fail(result["error"])
            summary_text = result.get("summary", "")
            findings = result.get("findings", [])
            risk_score, overall_risk, suggestion = calculate_risk(summary_text)
            return {
                "summary": summary_text,
                "overall_risk": overall_risk,
                "findings": findings,
                "risk_score": risk_score,
                "suggestion": suggestion,
                "source": "backend",
                "error": None,
            }
        except requests.exceptions.RequestException:
            # Backend was up a moment ago but the audit call failed --
            # fall through to the local pipeline rather than erroring out.
            use_backend = False

    # Local, in-process pipeline.
    if uploaded_file is not None:
        text_to_audit = _extract_text_locally(uploaded_file)
        if text_to_audit is None:
            return _fail("Sorry, we don't support this file type.")
    else:
        text_to_audit = raw_text

    summary_text, overall_risk = summarize_document(text_to_audit)
    findings = audit_text(text_to_audit)
    risk_score, overall_risk, suggestion = calculate_risk(summary_text)
    return {
        "summary": summary_text,
        "overall_risk": overall_risk,
        "findings": findings,
        "risk_score": risk_score,
        "suggestion": suggestion,
        "source": "local",
        "error": None,
    }


def render_result(result):
    """Renders one stored audit result block."""
    source_label = "🌐 Audited via backend" if result["source"] == "backend" else "💻 Audited locally"
    st.caption(source_label)
    display_summary(
        result["summary"], result["overall_risk"], result["risk_score"], result["suggestion"]
    )
    display_audit_results(result["findings"])
    st.download_button(
        "⬇️ Download report",
        data=build_report(result),
        file_name=f"tos_audit_{result['name']}.txt",
        mime="text/plain",
        key=f"dl_{result['name']}_{result['risk_score']}",
    )


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
            st.session_state.results = []
            for uploaded_file in uploaded_files:
                with st.spinner(f"Auditing {uploaded_file.name}… this can take a minute."):
                    result = run_audit(uploaded_file=uploaded_file)
                if result.get("error"):
                    st.error(result["error"])
                    continue
                result["name"] = uploaded_file.name
                st.session_state.results.append(result)

# --- TAB 2: PASTE TEXT ---
with tab2:
    pasted_tos = st.text_area(
        "Paste Terms of Service here:",
        height=320,
        key="tos_input_area",
        placeholder="Paste the full Terms of Service text you want to audit…",
    )

    if st.button("🚀 Start Audit on Pasted Text", key="audit_paste_btn", type="primary", use_container_width=True):
        if pasted_tos.strip():
            with st.spinner("Auditing pasted text… this can take a minute."):
                result = run_audit(raw_text=pasted_tos)
            if result.get("error"):
                st.error(result["error"])
            else:
                result["name"] = "pasted_text"
                st.session_state.results = [result]
        else:
            st.warning("Please paste some text before starting the audit.")


# ==========================================
# RESULTS  /  LANDING STATE
# ==========================================
st.divider()

if st.session_state.results:
    for i, result in enumerate(st.session_state.results):
        if len(st.session_state.results) > 1:
            st.markdown(f"### 📄 {result['name']}")
        render_result(result)
        if i < len(st.session_state.results) - 1:
            st.divider()
else:
    st.markdown("#### Why use ToS Auditor?")
    c1, c2, c3 = st.columns(3, gap="large")
    with c1:
        st.markdown(
            """
            <div class="feat">
                <div class="ico">🔍</div>
                <h4>Clause-by-clause scan</h4>
                <p>Every clause is checked for hidden traps, data-privacy risks, and unfair terms.</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with c2:
        st.markdown(
            """
            <div class="feat">
                <div class="ico">📚</div>
                <h4>Grounded in real law</h4>
                <p>RAG matches risky clauses to actual legal provisions — not guesswork.</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with c3:
        st.markdown(
            """
            <div class="feat">
                <div class="ico">⚡</div>
                <h4>Plain-language verdict</h4>
                <p>Get a clear risk score, summary, and downloadable report in seconds.</p>
            </div>
            """,
            unsafe_allow_html=True,
        )