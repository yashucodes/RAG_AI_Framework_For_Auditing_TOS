# frontend.py
import math
import os
import urllib.parse
from datetime import datetime

import requests
import streamlit as st

from app import process_pdf, process_image, process_docx, audit_text, summarize_document
from risk_score import calculate_risk

# ==========================================
# PAGE CONFIG
# ==========================================
st.set_page_config(
    page_title="ToS Auditor",
    page_icon=":scales:",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ==========================================
# HTML RENDER HELPER
# ==========================================
def _md_html(html_str):
    """
    st.markdown(..., unsafe_allow_html=True), but strips per-line leading
    whitespace first.

    Why this exists: Python's own source indentation gets baked into any
    multi-line f-string. Streamlit's markdown parser follows CommonMark,
    which requires an HTML block's first line to have 0-3 leading spaces --
    at 4+ spaces it's reclassified as a plain indented code block, and the
    raw tags get shown as literal text instead of being rendered. Every
    multi-line HTML snippet in this file goes through this helper so that
    bug can't quietly reappear anywhere.
    """
    dedented = "\n".join(line.strip() for line in html_str.strip("\n").splitlines())
    st.markdown(dedented, unsafe_allow_html=True)


# ==========================================
# BACKGROUND WATERMARK — open law book + Ashoka Chakra
# Tiled SVG data URI applied as a background-image (not a ::before overlay),
# so it can't disrupt Streamlit's own layout/stacking.
# ==========================================
def _build_chakra_spokes(cx, cy, r_inner, r_outer, count=24):
    spokes = []
    for i in range(count):
        angle = (2 * math.pi / count) * i
        x1 = cx + r_inner * math.cos(angle)
        y1 = cy + r_inner * math.sin(angle)
        x2 = cx + r_outer * math.cos(angle)
        y2 = cy + r_outer * math.sin(angle)
        spokes.append(f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" />')
    return "".join(spokes)


def _build_background_data_uri():
    # Muted red on near-black -- bright enough to read as a deliberate
    # motif, not so bright it fights with foreground text.
    stroke = "rgba(239,68,68,0.16)"
    chakra_spokes = _build_chakra_spokes(cx=150, cy=88, r_inner=10, r_outer=32, count=24)

    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="300" height="300" viewBox="0 0 300 300">
        <g fill="none" stroke="{stroke}" stroke-width="1.6" stroke-linecap="round">
            <path d="M150 130 L150 210" />
            <path d="M150 130 C 110 118, 70 122, 46 138 L 46 208 C 70 192, 110 188, 150 200 Z" />
            <path d="M150 130 C 190 118, 230 122, 254 138 L 254 208 C 230 192, 190 188, 150 200 Z" />
            <path d="M62 152 C 90 144, 118 146, 140 154" />
            <path d="M62 168 C 90 160, 118 162, 140 170" />
            <path d="M62 184 C 90 176, 118 178, 140 186" />
            <path d="M160 154 C 182 146, 210 144, 238 152" />
            <path d="M160 170 C 182 162, 210 160, 238 168" />
            <path d="M160 186 C 182 178, 210 176, 238 184" />
            <circle cx="150" cy="88" r="32" />
            <circle cx="150" cy="88" r="4" />
            {chakra_spokes}
        </g>
    </svg>"""

    encoded = urllib.parse.quote(svg)
    return f"data:image/svg+xml;utf8,{encoded}"


_BG_DATA_URI = _build_background_data_uri()

_STYLE_TEMPLATE = """
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=Fraunces:opsz,wght@9..144,600;9..144,700&display=swap');

    html, body, [class*="css"] { font-family: 'Inter', sans-serif; }

    /* --- Top toolbar (outside .stApp, needs its own selector) --- */
    [data-testid="stHeader"] {
        background-color: #0b0a0c !important;
    }

    /* --- Inline code spans, e.g. the `.pdf` `.docx` pills in the sidebar --- */
    .stApp code {
        background-color: #2a1414 !important;
        color: #f4b8b8 !important;
        border: 1px solid #3a1d1d;
    }

    /* --- Base app: near-black with the visible red watermark tiled on top --- */
    .stApp {
        background-color: #0b0a0c;
        background-image: url("__BG_DATA_URI__");
        background-repeat: repeat;
        background-size: 300px 300px;
        background-attachment: fixed;
    }

    .block-container { padding-top: 1.6rem; max-width: 1120px; }

    /* --- Default text: force light text on the dark base --- */
    .stApp, .stApp p, .stApp span, .stApp label, .stApp li,
    [data-testid="stMarkdownContainer"], [data-testid="stCaptionContainer"] {
        color: #ececec;
    }
    [data-testid="stCaptionContainer"] { color: #9b9b9f !important; }

    [data-testid="stSidebar"] {
        background-color: #111013;
        border-right: 1px solid #2a1414;
    }

    h1, h2, h3, .stSubheader { font-family: 'Fraunces', serif !important; color: #f5f0ee !important; }

    hr, [data-testid="stDivider"] { border-color: #2a1414 !important; }

    /* --- Hero header --- */
    .hero {
        background: linear-gradient(135deg, #000000 0%, #3f0d0d 55%, #b91c1c 100%);
        padding: 2.2rem 2.6rem;
        border-radius: 22px;
        color: #ffffff;
        margin-bottom: 1.4rem;
        box-shadow: 0 18px 44px rgba(185, 28, 28, 0.35);
        position: relative;
        overflow: hidden;
        border: 1px solid #7f1d1d;
    }
    .hero::after {
        content: "";
        position: absolute;
        right: -60px; top: -60px;
        width: 220px; height: 220px;
        background: radial-gradient(circle, rgba(239,68,68,0.28), transparent 70%);
        border-radius: 50%;
    }
    .hero-title { display: flex; align-items: center; gap: 1.3rem; }
    .hero-title svg { flex-shrink: 0; }
    .hero h1 {
        font-family: 'Fraunces', serif !important;
        color: #ffffff !important; margin: 0; font-size: 2.2rem; font-weight: 700; letter-spacing: -0.3px;
    }
    .hero p { color: #f4d4d4; margin: 0.6rem 0 0; font-size: 1.06rem; max-width: 640px; }

    /* --- Feature cards (landing) --- */
    .feat {
        background: #17141a;
        border: 1px solid #3a1d1d;
        border-radius: 16px;
        padding: 1.2rem 1.3rem;
        height: 100%;
        box-shadow: 0 4px 16px rgba(0,0,0,0.35);
        transition: transform .15s ease, box-shadow .15s ease, border-color .15s ease;
    }
    .feat:hover { transform: translateY(-3px); box-shadow: 0 12px 30px rgba(185,28,28,0.22); border-color: #b91c1c; }
    .feat h4 { margin: 0.3rem 0 0.25rem; font-size: 1.05rem; color: #f5f0ee; }
    .feat p  { margin: 0; font-size: 0.9rem; color: #a3a0a5; }

    /* --- Risk gauge (conic donut) --- */
    .gauge-wrap { display:flex; flex-direction:column; align-items:center; }
    .gauge {
        width: 168px; height: 168px; border-radius: 50%;
        display: flex; align-items: center; justify-content: center;
        box-shadow: 0 8px 26px rgba(0,0,0,0.5);
    }
    .gauge-inner {
        width: 128px; height: 128px; border-radius: 50%;
        background: #17141a;
        display: flex; flex-direction: column;
        align-items: center; justify-content: center;
    }
    .gauge-inner .num { font-family: 'Fraunces', serif; font-size: 2.6rem; font-weight: 700; line-height: 1; color: #f5f0ee; }
    .gauge-inner .num small { font-size: 1rem; color: #8a8790; font-weight: 600; }
    .pill {
        display:inline-block; margin-top:0.7rem;
        padding: 0.28rem 0.9rem; border-radius: 999px;
        font-size: 0.82rem; font-weight: 700; letter-spacing:0.3px;
        color:#ffffff;
    }
    .pill-high   { background:#ef4444; }
    .pill-medium { background:#f59e0b; }
    .pill-low    { background:#22c55e; }

    /* --- Finding cards --- */
    .finding {
        border-radius: 14px;
        padding: 1rem 1.2rem;
        margin-bottom: 0.7rem;
        border-left: 6px solid;
        box-shadow: 0 2px 12px rgba(0,0,0,0.35);
    }
    .finding-high  { border-color: #ef4444; background: rgba(239,68,68,0.10); }
    .finding-warn  { border-color: #f59e0b; background: rgba(245,158,11,0.10); }
    .finding-head  { display:flex; align-items:center; gap:0.5rem; flex-wrap:wrap; }
    .finding-title { font-weight:700; font-size:1.02rem; color: #f5f0ee; }
    .chip {
        font-size:0.72rem; font-weight:700; padding:0.15rem 0.6rem;
        border-radius:999px; color:#fff; text-transform:uppercase; letter-spacing:0.4px;
    }
    .chip-high { background:#ef4444; }
    .chip-warn { background:#f59e0b; }
    .finding-meta  { font-size:0.82rem; color:#b8b5ba; margin-top:0.3rem; }
    .quote {
        font-style: italic;
        color: #d8d5d8;
        border-left: 3px solid #4a2323;
        padding-left: 0.8rem;
        margin: 0.4rem 0;
    }

    /* --- Backend status badge --- */
    .status { display:flex; align-items:center; gap:0.5rem; font-size:0.88rem; font-weight:600; color:#ececec; }
    .dot { width:10px; height:10px; border-radius:50%; display:inline-block; }
    .dot-on  { background:#22c55e; box-shadow:0 0 0 4px rgba(34,197,94,0.18); }
    .dot-off { background:#8a8790; box-shadow:0 0 0 4px rgba(138,135,144,0.18); }

    /* --- Inputs --- */
    .stTextArea textarea, [data-testid="stFileUploaderDropzone"] {
        background-color: #17141a !important;
        border: 1px solid #3a1d1d !important;
        color: #ececec !important;
    }

    /* --- File uploader's internal "Browse files" button (separate from .stButton) --- */
    [data-testid="stFileUploaderDropzone"] button {
        background-color: #b91c1c !important;
        color: #ffffff !important;
        border: 1px solid #ef4444 !important;
    }
    [data-testid="stFileUploaderDropzone"] button:hover {
        background-color: #ef4444 !important;
    }

    /* --- Buttons --- */
    .stButton>button {
        border-radius: 12px;
        font-weight: 600;
        background-color: #b91c1c;
        color: #ffffff;
        border: 1px solid #ef4444;
    }
    .stButton>button:hover {
        background-color: #ef4444;
        border-color: #ef4444;
        color: #ffffff;
    }

    /* --- Tabs --- */
    .stTabs [data-baseweb="tab-list"] { border-bottom: 1px solid #3a1d1d; }
    .stTabs [data-baseweb="tab"] { color: #a3a0a5; }
    .stTabs [aria-selected="true"] { color: #ef4444 !important; }

    /* --- Metrics --- */
    [data-testid="stMetricValue"] { color: #f5f0ee; }
    [data-testid="stMetricLabel"] { color: #a3a0a5; }
</style>
"""

_md_html(_STYLE_TEMPLATE.replace("__BG_DATA_URI__", _BG_DATA_URI))

# Small inline "scales of justice" mark used in the hero, instead of an emoji glyph.
_SCALES_SVG = (
    '<svg width="40" height="40" viewBox="0 0 40 40" fill="none" xmlns="http://www.w3.org/2000/svg">'
    '<line x1="20" y1="4" x2="20" y2="32" stroke="#ffffff" stroke-width="2" stroke-linecap="round"/>'
    '<line x1="6" y1="10" x2="34" y2="10" stroke="#ffffff" stroke-width="2" stroke-linecap="round"/>'
    '<path d="M6 10 L2 20 A6 6 0 0 0 14 20 Z" stroke="#ffffff" stroke-width="1.6" fill="none" stroke-linejoin="round"/>'
    '<path d="M34 10 L30 20 A6 6 0 0 0 42 20 Z" stroke="#ffffff" stroke-width="1.6" fill="none" stroke-linejoin="round"/>'
    '<rect x="12" y="32" width="16" height="3.5" rx="1.5" fill="#ffffff"/>'
    '<circle cx="20" cy="6" r="2.4" fill="#ffffff"/>'
    "</svg>"
)

# ==========================================
# CONFIG
# ==========================================
# The URL of our FastAPI backend (run separately with
# `uvicorn app:app --reload`). If it isn't running, every audit call
# below automatically falls back to running the pipeline in-process
# instead -- so the app works either way.
BACKEND_URL = "http://127.0.0.1:8000"
HEALTHCHECK_TIMEOUT_SECONDS = 2
AUDIT_TIMEOUT_SECONDS = 600

UPLOAD_FOLDER = "temp_uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

RISK_META = {
    "high": ("#ef4444", "High Risk", "pill-high"),
    "medium": ("#f59e0b", "Medium Risk", "pill-medium"),
    "low": ("#22c55e", "Low Risk", "pill-low"),
}

if "results" not in st.session_state:
    st.session_state.results = []


# ==========================================
# BACKEND STATUS
# ==========================================
@st.cache_data(ttl=8, show_spinner=False)
def backend_is_up():
    try:
        r = requests.get(f"{BACKEND_URL}/", timeout=HEALTHCHECK_TIMEOUT_SECONDS)
        return r.status_code == 200
    except requests.exceptions.RequestException:
        return False


# ==========================================
# HERO + SIDEBAR
# ==========================================
_md_html(f"""
<div class="hero">
<div class="hero-title">
{_SCALES_SVG}
<h1>Legal ToS Auditor</h1>
</div>
<p>An AI-assisted legal audit tool — it reads long Terms of Service agreements and flags
sneaky, unfair, or contradictory clauses against Indian law, so you don't have to.</p>
</div>
""")

with st.sidebar:
    st.subheader("Engine Status")
    online = backend_is_up()
    if online:
        _md_html('<div class="status"><span class="dot dot-on"></span> FastAPI backend online</div>')
    else:
        _md_html('<div class="status"><span class="dot dot-off"></span> Running in local mode</div>')
        st.caption("Start the backend with `uvicorn app:app --reload` for shared/API use.")

    st.divider()
    st.header("How It Works")
    st.markdown(
        """
        1. **Upload** a ToS file or **paste** the text.
        2. The audit engine splits it into clauses and scans each one.
        3. **RAG** matches risky clauses to real legal provisions.
        4. You get a **risk score**, a clear verdict, and the exact
           clauses flagged.
        """
    )
    st.divider()
    st.subheader("Supported Files")
    st.markdown("- PDF (`.pdf`)\n- Word (`.docx`)\n- Images (`.png`, `.jpg`, `.jpeg`)")
    st.divider()
    if st.session_state.results:
        if st.button("Clear Results", use_container_width=True):
            st.session_state.results = []
            st.rerun()
    st.caption("Powered by RAG · This is an assistive tool, not legal advice.")


# ==========================================
# DISPLAY HELPERS
# ==========================================
def display_overview(overview_text, overall_risk, risk_score, suggestion):
    """Renders the top-level audit verdict: donut risk gauge + plain-language overview."""
    color, label, pill_class = RISK_META.get(overall_risk, RISK_META["medium"])
    pct = max(0, min(int(round(risk_score * 10)), 100))

    st.subheader("Audit Overview")
    col_score, col_text = st.columns([1, 2.4], gap="large")

    with col_score:
        _md_html(f"""
        <div class="gauge-wrap">
        <div class="gauge" style="background: conic-gradient({color} {pct}%, #2a2a2e 0);">
        <div class="gauge-inner">
        <span class="num">{risk_score}<small>/10</small></span>
        </div>
        </div>
        <span class="pill {pill_class}">{label}</span>
        </div>
        """)

    with col_text:
        st.write(overview_text)
        st.info(f"**Suggestion:** {suggestion}")


def display_audit_results(findings):
    if isinstance(findings, dict):
        findings = [findings]

    if not findings:
        st.success("No risky or contradictory clauses detected.")
        return

    high_risk_count = sum(
        1 for f in findings
        if f.get("risk_category") in ("hidden_trap", "data_privacy_risk", "high_risk")
    )
    contradiction_count = sum(
        1 for f in findings
        if f.get("risk_category") in ("contradiction", "medium_risk")
    )

    st.subheader("Detailed Findings")
    m1, m2, m3 = st.columns(3)
    m1.metric("Total findings", len(findings))
    m2.metric("High risk", high_risk_count)
    m3.metric("Contradictions", contradiction_count)

    for f in findings:
        clause_number = f.get("clause_number", "?")
        clause_text = f.get("clause_text", "")
        risk_category = f.get("risk_category", "compliant")
        explanation = f.get("explanation", "")
        legal_citation = f.get("legal_citation", "")
        law_excerpt = f.get("law_excerpt", "")

        if risk_category in ("hidden_trap", "data_privacy_risk", "high_risk"):
            _md_html(f"""
            <div class="finding finding-high">
            <div class="finding-head">
            <span class="chip chip-high">High Risk</span>
            <span class="finding-title">Clause #{clause_number}</span>
            </div>
            <div class="finding-meta">Violates: {legal_citation}</div>
            </div>
            """)
            with st.expander(f"View flagged clause #{clause_number}"):
                _md_html(f'<div class="quote">"{clause_text}"</div>')
                if explanation:
                    st.markdown(f"**Why it's risky:** {explanation}")
                if law_excerpt:
                    st.markdown(f"**Matched law text:** *\"{law_excerpt}\"*")

        elif risk_category in ("contradiction", "medium_risk"):
            _md_html(f"""
            <div class="finding finding-warn">
            <div class="finding-head">
            <span class="chip chip-warn">Contradiction</span>
            <span class="finding-title">Clauses #{clause_number}</span>
            </div>
            <div class="finding-meta">{legal_citation or "Internal inconsistency"}</div>
            </div>
            """)
            with st.expander(f"View conflicting clauses #{clause_number}"):
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
        "AUDIT OVERVIEW",
        "-" * 60,
        result["overview"],
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
    safe_name = os.path.basename(uploaded_file.name)
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
    def _fail(msg):
        return {"error": msg}

    use_backend = backend_is_up()

    if use_backend:
        try:
            result = _audit_via_backend(uploaded_file, raw_text)
            if "error" in result:
                return _fail(result["error"])
            overview_text = result.get("summary", "")
            findings = result.get("findings", [])
            risk_score, overall_risk, suggestion = calculate_risk(overview_text)
            return {
                "overview": overview_text,
                "overall_risk": overall_risk,
                "findings": findings,
                "risk_score": risk_score,
                "suggestion": suggestion,
                "source": "backend",
                "error": None,
            }
        except requests.exceptions.RequestException:
            use_backend = False

    if uploaded_file is not None:
        text_to_audit = _extract_text_locally(uploaded_file)
        if text_to_audit is None:
            return _fail("Sorry, we don't support this file type.")
    else:
        text_to_audit = raw_text

    overview_text, overall_risk = summarize_document(text_to_audit)
    findings = audit_text(text_to_audit)
    risk_score, overall_risk, suggestion = calculate_risk(overview_text)
    return {
        "overview": overview_text,
        "overall_risk": overall_risk,
        "findings": findings,
        "risk_score": risk_score,
        "suggestion": suggestion,
        "source": "local",
        "error": None,
    }


def render_result(result):
    source_label = "Audited via backend" if result["source"] == "backend" else "Audited locally"
    st.caption(source_label)
    display_overview(
        result["overview"], result["overall_risk"], result["risk_score"], result["suggestion"]
    )
    display_audit_results(result["findings"])
    st.download_button(
        "Download Report",
        data=build_report(result),
        file_name=f"tos_audit_{result['name']}.txt",
        mime="text/plain",
        key=f"dl_{result['name']}_{result['risk_score']}",
    )


# ==========================================
# MAIN TABS
# ==========================================
tab1, tab2 = st.tabs(["Upload Document", "Paste Text"])

with tab1:
    uploaded_files = st.file_uploader(
        "Upload your ToS documents",
        type=["pdf", "png", "jpg", "jpeg", "docx"],
        accept_multiple_files=True,
        help="PDF, DOCX, or image files are supported.",
    )

    if uploaded_files:
        st.success(f"Uploaded {len(uploaded_files)} file(s).")

        if st.button("Start Audit on Files", type="primary", use_container_width=True):
            st.session_state.results = []
            for uploaded_file in uploaded_files:
                with st.spinner(f"Auditing {uploaded_file.name}... this can take a minute."):
                    result = run_audit(uploaded_file=uploaded_file)
                if result.get("error"):
                    st.error(result["error"])
                    continue
                result["name"] = uploaded_file.name
                st.session_state.results.append(result)

with tab2:
    pasted_tos = st.text_area(
        "Paste Terms of Service here:",
        height=320,
        key="tos_input_area",
        placeholder="Paste the full Terms of Service text you want to audit...",
    )

    if st.button("Start Audit on Pasted Text", key="audit_paste_btn", type="primary", use_container_width=True):
        if pasted_tos.strip():
            with st.spinner("Auditing pasted text... this can take a minute."):
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
            st.markdown(f"### {result['name']}")
        render_result(result)
        if i < len(st.session_state.results) - 1:
            st.divider()
else:
    st.markdown("#### Why Use ToS Auditor?")
    c1, c2, c3 = st.columns(3, gap="large")
    with c1:
        _md_html("""
        <div class="feat">
        <h4>Clause-by-clause scan</h4>
        <p>Every clause is checked for hidden traps, data-privacy risks, and unfair terms.</p>
        </div>
        """)
    with c2:
        _md_html("""
        <div class="feat">
        <h4>Grounded in real law</h4>
        <p>RAG matches risky clauses to actual Indian legal provisions -- not guesswork.</p>
        </div>
        """)
    with c3:
        _md_html("""
        <div class="feat">
        <h4>Clear, direct verdict</h4>
        <p>Get a risk score and the exact clauses flagged in seconds.</p>
        </div>
        """)