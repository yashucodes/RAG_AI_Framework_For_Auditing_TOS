# app.py (The Kitchen / Backend)
import re
import os
import json
from dotenv import load_dotenv
from fastapi import FastAPI, UploadFile, File, Form
from langchain_community.document_loaders import PyPDFLoader, Docx2txtLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.documents import Document
from PIL import Image
import pytesseract
import shutil
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS
from google import genai
from google.genai import types

load_dotenv()

import time
from google.genai import errors as genai_errors

gemini_client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))
GEMINI_MODEL = "gemini-flash-lite-latest"

RATE_LIMIT_WAIT_SECONDS = 45
MAX_RATE_LIMIT_RETRIES = 5


def _call_gemini_json(prompt, schema):
    """
    Calls Gemini with a prompt and a JSON schema and returns the parsed
    JSON response. Automatically retries on free-tier rate limit errors.
    """
    for attempt in range(MAX_RATE_LIMIT_RETRIES):
        try:
            response = gemini_client.models.generate_content(
                model=GEMINI_MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=schema,
                ),
            )
            return json.loads(response.text)
        except genai_errors.ClientError as e:
            is_rate_limit = getattr(e, "code", None) == 429
            if is_rate_limit and attempt < MAX_RATE_LIMIT_RETRIES - 1:
                print(
                    f"Free-tier rate limit hit -- waiting {RATE_LIMIT_WAIT_SECONDS}s "
                    f"before retrying (attempt {attempt + 1}/{MAX_RATE_LIMIT_RETRIES})..."
                )
                time.sleep(RATE_LIMIT_WAIT_SECONDS)
                continue
            raise


# --- SETUP ROBOT EYES ---
def _locate_tesseract():
    # Allow user to override with env vars set by deployment or local dev.
    env_checks = [os.environ.get("TESSERACT_CMD"), os.environ.get("TESSERACT_PATH")]
    for p in env_checks:
        if p and os.path.exists(p):
            return p

    # If tesseract is on PATH, shutil.which will find it.
    which = shutil.which("tesseract")
    if which:
        return which

    # Common Windows install locations
    common = [
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
        r"C:\Tesseract-OCR\tesseract.exe",
    ]
    for p in common:
        if os.path.exists(p):
            return p

    return None


_TESSERACT_CMD = _locate_tesseract()
if _TESSERACT_CMD:
    pytesseract.pytesseract.tesseract_cmd = _TESSERACT_CMD
else:
    # Do not set tesseract_cmd; let callers handle the missing binary.
    print("WARNING: tesseract executable not found. OCR will fail for images unless Tesseract is installed and on PATH.")


# ==========================================
# RECIPES (Chop the food)
# ==========================================
def process_pdf(file_path):
    loader = PyPDFLoader(file_path)
    pages = loader.load()

    print("Chopping text into bite-sized chunks...")
    text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=100)
    chunks = text_splitter.split_documents(pages)

    print(f"DONE! I read {len(pages)} pages and chopped them into {len(chunks)} small chunks.")
    return chunks


# ==========================================
# 2. IMAGE RECIPE
# ==========================================
def process_image(file_path):
    """
    Extracts text from an image using OCR and returns it as a plain
    string — the same format that process_pdf() and process_docx()
    produce after going through _extract_text_from_chunks().

    FIX: Previously this returned a list of Document chunks, which caused
    an AttributeError when summarize_document() called .strip() on it.
    Now it returns a plain string directly so all three file types
    (PDF, DOCX, image) produce the same output type for the audit pipeline.
    """
    my_picture = Image.open(file_path)
    try:
        raw_text = pytesseract.image_to_string(my_picture)
        return raw_text  # ✅ plain string — consistent with PDF/DOCX after extraction
    except pytesseract.pytesseract.TesseractNotFoundError:
        raise RuntimeError(
            "Tesseract OCR executable not found. Install Tesseract (https://github.com/tesseract-ocr/tesseract) "
            "and ensure it's on your PATH, or set the TESSERACT_CMD/TESSERACT_PATH environment variable to the tesseract.exe location."
        )


def process_docx(file_path):
    loader = Docx2txtLoader(file_path)
    pages = loader.load()

    print("Chopping text into bite-sized chunks...")
    text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=100)
    return text_splitter.split_documents(pages)


def process_text(raw_text):
    print("Reading pasted text...")
    doc = [Document(page_content=raw_text)]
    text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=100)
    return text_splitter.split_documents(doc)


# ==========================================
# 5. THE WALKIE-TALKIE (SEARCH DATABASE)
# ==========================================
law_embeddings = HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")

LAW_CANDIDATES_K = 5

# The FAISS index is loaded lazily and cached, so we don't re-read it
# from disk on every single clause lookup.
_law_vector_db = None


def _get_law_vector_db():
    global _law_vector_db
    if _law_vector_db is None:
        _law_vector_db = FAISS.load_local(
            "./faiss_db",
            law_embeddings,
            allow_dangerous_deserialization=True,
        )
    return _law_vector_db

_LAW_RELEVANCE_SCHEMA = {
    "type": "object",
    "properties": {
        "relevant": {"type": "boolean"},
        "excerpt_number": {"type": "integer"},
        "reasoning": {"type": "string"},
    },
    "required": ["relevant", "reasoning"],
}


def search_indian_laws(query_text):
    print(f"Searching Archive for: '{query_text[:50]}...'")

    vector_db = _get_law_vector_db()
    candidates = vector_db.similarity_search(query_text, k=LAW_CANDIDATES_K)
    if not candidates:
        return []

    excerpt_list = "\n\n".join(
        f"[{i + 1}] {doc.page_content[:500]}"
        for i, doc in enumerate(candidates)
    )

    prompt = f"""You are a legal analyst matching a Terms of Service clause to the most
relevant provision from a set of candidate law excerpts.

Flagged clause:
\"\"\"{query_text}\"\"\"

Candidate law excerpts:
{excerpt_list}

Choose the SINGLE candidate excerpt number that is most relevant to this
clause. Only choose from the excerpts given -- do not invent or modify
excerpt text.

Be conservative: these candidates were retrieved by keyword/topic
similarity, so some may share vocabulary with the clause (e.g. "third
party", "data") without actually addressing the same substantive issue.
Only mark relevant as true if the excerpt genuinely speaks to the
specific practice in the clause -- e.g. imposes a real obligation,
restriction, or liability standard that the clause's conduct would
satisfy or violate. Sharing a topic or keyword is NOT enough on its
own. If you are not confident any candidate substantively applies, set
relevant to false and excerpt_number to null -- an honest "no match" is
better than a weak, unconfident match."""

    result = _call_gemini_json(prompt, _LAW_RELEVANCE_SCHEMA)

    if not result.get("relevant") or result.get("excerpt_number") is None:
        print("Gemini judged no candidate law excerpt as relevant.")
        return []

    idx = result["excerpt_number"] - 1
    if idx < 0 or idx >= len(candidates):
        return []

    return [candidates[idx]]


def format_citation(doc):
    """Builds a clean, human-readable citation from a law document's metadata."""
    source = doc.metadata.get("source", "Unknown source")
    filename = os.path.splitext(os.path.basename(source))[0]
    display_name = filename.replace("_", " ").replace("-", " ").strip()
    return display_name


# ==========================================
# 6. CLAUSE SPLITTER
# ==========================================
def split_into_clauses(raw_text):
    """
    Splits pasted ToS text into individual clauses.
    Works whether the text has numbered sections (1. 2. 3...) or just
    paragraph breaks — falls back to paragraphs if no numbering is found.
    """
    text = raw_text.strip()

    numbered_split = re.split(r'\n(?=\d+\.\s+[A-Z])', text)
    numbered_split = [c.strip() for c in numbered_split if c.strip()]

    if len(numbered_split) > 1:
        return numbered_split

    paragraph_split = [p.strip() for p in text.split("\n\n") if p.strip()]
    if len(paragraph_split) > 1:
        return paragraph_split

    return [text]


# ==========================================
# 7. SEMANTIC RISK DETECTION (Gemini LLM-based)
# ==========================================
RISK_CATEGORIES = ["data_privacy_risk", "liability_waiver", "retention_risk", "termination_risk", "compliant"]

_RISK_CLASSIFICATION_SCHEMA = {
    "type": "object",
    "properties": {
        "category": {"type": "string", "enum": RISK_CATEGORIES},
        "confidence": {"type": "number"},
        "reason": {"type": "string"},
        "excerpt": {"type": "string"},
    },
    "required": ["category", "confidence", "reason", "excerpt"],
}

_RISK_CLASSIFICATION_PROMPT = """You are a legal analyst reviewing a single clause from a Terms of
Service agreement for consumer-unfriendly risk. Classify the clause into
exactly one of these categories:

- data_privacy_risk: allows sharing/selling user data with third parties
  without clear consent, or collects more data than needed for the
  stated purpose. Do NOT flag a clause just because it mentions
  "third-party" services or partners in passing (e.g. "we use
  third-party payment/storage providers, their own policies apply") --
  that is standard boilerplate disclosure, not a data-sharing risk,
  unless the clause itself states that the COMPANY shares or discloses
  the USER's data with those third parties.
- liability_waiver: disclaims the company's liability for security
  breaches, damages, or unauthorized access.
- retention_risk: allows the company to keep user data indefinitely or
  for an unspecified period after account closure.
- termination_risk: allows the company to terminate or suspend a user's
  account without notice or explanation.
- compliant: none of the above risks apply. This includes clauses that
  actively PROMISE something protective -- e.g. promising data deletion
  within a stated period, accepting liability for the company's own
  negligence, or requiring notice before termination. Do not flag a
  protective clause just because it mentions the same general topic as
  a risky one.

Clause:
\"\"\"{clause}\"\"\"

Respond with:
- the single best-fitting category
- a confidence score from 0 to 1
- a one-sentence reason
- excerpt: the EXACT sentence or short phrase (at most 2 sentences),
  copied word-for-word from the clause above, that most directly causes
  this classification. This is what will be shown to the user instead
  of the full clause, so it must be the specific problem text, not a
  summary or paraphrase. If the category is compliant, excerpt can be
  an empty string."""


def classify_risk(clause_text):
    """
    Returns (risk_category, confidence, reason, excerpt).
    """
    text = re.sub(r'^\d+\.\s+[A-Z][A-Z \-&]*\n', '', clause_text.strip())
    prompt = _RISK_CLASSIFICATION_PROMPT.format(clause=text)
    result = _call_gemini_json(prompt, _RISK_CLASSIFICATION_SCHEMA)
    return (
        result.get("category", "compliant"),
        float(result.get("confidence", 0.0)),
        result.get("reason", ""),
        result.get("excerpt", ""),
    )


# ==========================================
# 8. CONTRADICTION DETECTION (Gemini LLM-based)
# ==========================================
_CONTRADICTION_SCHEMA = {
    "type": "object",
    "properties": {
        "contradictions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "clause_a": {"type": "integer"},
                    "clause_b": {"type": "integer"},
                    "excerpt_a": {"type": "string"},
                    "excerpt_b": {"type": "string"},
                    "explanation": {"type": "string"},
                },
                "required": ["clause_a", "clause_b", "excerpt_a", "excerpt_b", "explanation"],
            },
        }
    },
    "required": ["contradictions"],
}


def find_contradictions(clauses):
    """
    Sends the full numbered list of clauses to Gemini and returns
    contradiction pairs as (clause_num_a, clause_num_b, excerpt_a,
    excerpt_b, explanation) tuples.
    """
    if len(clauses) < 2:
        return []

    numbered_list = "\n\n".join(f"{i + 1}. {clause}" for i, clause in enumerate(clauses))

    prompt = f"""You are a legal analyst reviewing a Terms of Service document for
internal contradictions -- pairs of clauses where one promises or grants
the user something, and another clause elsewhere quietly undercuts or
reverses that same promise.

Numbered clauses:
{numbered_list}

Identify any pairs of clause numbers that genuinely contradict each
other in this way. Do not flag pairs that are merely about the same
general topic without an actual conflict in meaning. Return an empty
list if there are no contradictions.

For each contradiction found, also give:
- excerpt_a: the EXACT sentence, copied word-for-word from clause_a,
  that makes the promise/grant.
- excerpt_b: the EXACT sentence, copied word-for-word from clause_b,
  that undercuts or reverses it.
These excerpts are what gets shown to the user, so they must be the
specific conflicting text, not the whole clause or a summary."""

    result = _call_gemini_json(prompt, _CONTRADICTION_SCHEMA)

    contradictions = []
    for pair in result.get("contradictions", []):
        i, j = pair.get("clause_a"), pair.get("clause_b")
        if i is None or j is None:
            continue
        i, j = i - 1, j - 1
        if 0 <= i < len(clauses) and 0 <= j < len(clauses) and i != j:
            excerpt_a = pair.get("excerpt_a") or clauses[i]
            excerpt_b = pair.get("excerpt_b") or clauses[j]
            explanation = pair.get("explanation", "These two clauses appear to conflict with each other.")
            contradictions.append((i + 1, j + 1, excerpt_a, excerpt_b, explanation))

    return contradictions


# ==========================================
# 8.5. DOCUMENT SUMMARY (Gemini LLM-based)
# ==========================================
_SUMMARY_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "overall_risk": {
            "type": "string",
            "enum": ["low", "medium", "high"],
        },
    },
    "required": ["summary", "overall_risk"],
}


def summarize_document(raw_text):
    """
    Returns (summary_text, overall_risk) where overall_risk is one of
    "low", "medium", "high". Falls back gracefully if the call fails.
    """
    # FIX: guard against raw_text being a list instead of a string.
    # This can happen if a caller passes process_image() output directly
    # without going through _extract_text_from_chunks() first.
    if isinstance(raw_text, list):
        raw_text = " ".join(
            c.page_content if hasattr(c, "page_content") else str(c)
            for c in raw_text
        )

    text = raw_text.strip()
    if not text:
        return "No readable text was found in this document.", "low"

    excerpt = text[:6000]

    prompt = f"""You are a legal analyst giving a everyday user a quick, plain-language
overview of a Terms of Service document before they read a detailed
clause-by-clause audit.

Document text:
\"\"\"{excerpt}\"\"\"

Write a short summary (3-4 sentences, no legal jargon) covering:
- what service/company this agreement is for, if identifiable
- the main things it covers (e.g. data use, payments, account rules)
- a plain-language sense of how consumer-friendly or one-sided it reads overall

Also rate the overall_risk as "low", "medium", or "high" based on how
consumer-unfriendly the document reads as a whole."""

    try:
        result = _call_gemini_json(prompt, _SUMMARY_SCHEMA)
        return (
            result.get("summary", "Summary unavailable."),
            result.get("overall_risk", "medium"),
        )
    except Exception as e:
        print(f"summarize_document failed: {e}")
        return "Summary unavailable for this document.", "medium"


# ==========================================
# 9. FULL AUDIT PIPELINE
# ==========================================
def audit_text(raw_text):
    """
    Takes raw pasted (or extracted) ToS text and returns a list of
    finding dicts ready for frontend.py's display_audit_results().
    """
    # FIX: same list guard as summarize_document — if a list of chunks
    # is passed in, stitch them into a single string first.
    if isinstance(raw_text, list):
        raw_text = " ".join(
            c.page_content if hasattr(c, "page_content") else str(c)
            for c in raw_text
        )

    clauses = split_into_clauses(raw_text)
    findings = []

    # --- Pass 1: per-clause semantic risk check ---
    for clause_number, clause in enumerate(clauses, start=1):
        risk_category, score, reason, excerpt = classify_risk(clause)
        if risk_category != "compliant":
            matching_laws = search_indian_laws(clause)
            if not matching_laws:
                continue

            citation = format_citation(matching_laws[0])
            law_excerpt = matching_laws[0].page_content[:200].strip() + "..."

            findings.append({
                "clause_number": clause_number,
                "clause_text": excerpt if excerpt else clause,
                "risk_category": "high_risk",
                "explanation": f"{reason} (confidence {score:.2f})" if reason else f"Detected: {risk_category.replace('_', ' ')} (confidence {score:.2f})",
                "legal_citation": citation,
                "law_excerpt": law_excerpt,
            })

    # --- Pass 2: contradiction check across clause pairs ---
    all_pairs = find_contradictions(clauses)

    for clause_num_a, clause_num_b, excerpt_a, excerpt_b, explanation in all_pairs:
        findings.append({
            "clause_number": f"{clause_num_a} & {clause_num_b}",
            "clause_text": f"{excerpt_a}\n\n—vs—\n\n{excerpt_b}",
            "risk_category": "contradiction",
            "explanation": explanation,
            "legal_citation": "Internal inconsistency — flagged for manual review",
            "law_excerpt": "",
        })

    return findings


# ==========================================
# 10. THE DRIVE-THRU WINDOWS (FastAPI)
# ==========================================
app = FastAPI(title="ToS Auditor Kitchen")

UPLOAD_FOLDER = "temp_uploads"
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)


@app.get("/")
def check_kitchen_status():
    return {"message": "Hello! The Kitchen Drive-Thru is OPEN!"}


def _extract_text_from_chunks(chunks):
    """Stitches a list of Document chunks back into one plain string."""
    return " ".join(c.page_content for c in chunks)


# Window 1: For Pasted Text
@app.post("/audit-text/")
def audit_pasted_text(raw_text: str = Form(...)):
    summary_text, overall_risk = summarize_document(raw_text)
    findings = audit_text(raw_text)
    return {
        "summary": summary_text,
        "overall_risk": overall_risk,
        "findings": findings,
    }


# Window 2: For Uploaded Files (PDFs, Images, Word Docs)
@app.post("/audit-file/")
def audit_uploaded_file(file: UploadFile = File(...)):
    print(f"Drive-Thru received a file: {file.filename}")

    # Sanitize the filename to strip any directory components -- this
    # prevents path-traversal attacks (e.g. "../../etc/passwd").
    safe_name = os.path.basename(file.filename or "")
    if not safe_name:
        return {"error": "Invalid file name."}

    temp_filepath = os.path.join(UPLOAD_FOLDER, safe_name)
    name_lower = safe_name.lower()

    try:
        with open(temp_filepath, "wb") as f:
            f.write(file.file.read())

        try:
            if name_lower.endswith(".pdf"):
                text_to_audit = _extract_text_from_chunks(process_pdf(temp_filepath))
            elif name_lower.endswith((".png", ".jpg", ".jpeg")):
                # process_image() returns a plain string directly.
                text_to_audit = process_image(temp_filepath)
            elif name_lower.endswith(".docx"):
                text_to_audit = _extract_text_from_chunks(process_docx(temp_filepath))
            else:
                return {"error": "Sorry, we don't cook this type of file!"}
        except Exception as e:
            # Return a friendly JSON error instead of letting a 500 bubble up
            return {"error": str(e)}
    finally:
        # Always clean up the temp file, even if processing raised.
        if os.path.exists(temp_filepath):
            os.remove(temp_filepath)

    summary_text, overall_risk = summarize_document(text_to_audit)
    findings = audit_text(text_to_audit)

    return {
        "summary": summary_text,
        "overall_risk": overall_risk,
        "findings": findings,
    }


# ==========================================
# LOCAL TESTING
# ==========================================
if __name__ == "__main__":
    print("\n--- Running Local Test ---")
    try:
        test_chunks = process_pdf("sample.pdf")
        print("Success! The app.py backend is working perfectly on its own.")
    except Exception as e:
        print(f"Could not test sample.pdf. Make sure the file exists! Error: {e}")