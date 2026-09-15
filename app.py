import re
import os
import json
import time
import math
from typing import List, Dict, Tuple

from dotenv import load_dotenv
from fastapi import FastAPI, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from langchain_community.document_loaders import PyPDFLoader, Docx2txtLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.documents import Document
from PIL import Image
import pytesseract
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS
from google import genai
from google.genai import types
from google.genai import errors as genai_errors


# ==========================================
# 0. CONFIGURATION
# ==========================================
load_dotenv()

gemini_client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))
GEMINI_MODEL = "gemini-flash-lite-latest"

RATE_LIMIT_WAIT_SECONDS = 45
MAX_RATE_LIMIT_RETRIES = 5

UPLOAD_FOLDER = "temp_uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)


# ==========================================
# 1. GEMINI HELPER
# ==========================================
def _call_gemini_json(prompt, schema):
    """
    Call Gemini with a JSON schema and return the parsed JSON response.
    Retries automatically on free-tier rate-limit errors.
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


# ==========================================
# 2. OCR SETUP
# ==========================================
pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"


# ==========================================
# 3. DOCUMENT PROCESSING
# ==========================================
def process_pdf(file_path):
    loader = PyPDFLoader(file_path)
    pages = loader.load()

    print("Chopping text into bite-sized chunks...")
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000,
        chunk_overlap=100,
    )
    chunks = text_splitter.split_documents(pages)

    print(
        f"DONE! I read {len(pages)} pages and chopped them into {len(chunks)} small chunks."
    )
    return chunks


def process_image(file_path):
    my_picture = Image.open(file_path)
    raw_text = pytesseract.image_to_string(my_picture)
    return raw_text


def process_docx(file_path):
    loader = Docx2txtLoader(file_path)
    pages = loader.load()

    print("Chopping text into bite-sized chunks...")
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000,
        chunk_overlap=100,
    )
    return text_splitter.split_documents(pages)


def process_text(raw_text):
    print("Reading pasted text...")
    doc = [Document(page_content=raw_text)]
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000,
        chunk_overlap=100,
    )
    return text_splitter.split_documents(doc)


# ==========================================
# 4. LAW RAG DATABASE
# ==========================================
law_embeddings = HuggingFaceEmbeddings(
    model_name="sentence-transformers/all-MiniLM-L6-v2"
)

LAW_CANDIDATES_K = 5
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

Choose the SINGLE candidate excerpt number that is most relevant to this clause.
Only mark relevant as true if the excerpt genuinely speaks to the specific practice in the clause."""

    try:
        result = _call_gemini_json(prompt, _LAW_RELEVANCE_SCHEMA)

        if not result.get("relevant") or result.get("excerpt_number") is None:
            return []

        idx = result["excerpt_number"] - 1
        if idx < 0 or idx >= len(candidates):
            return []

        return [candidates[idx]]

    except Exception as e:
        print(f"search_indian_laws error: {e}")
        return []


def format_citation(doc):
    source = doc.metadata.get("source", "Unknown source")
    filename = os.path.splitext(os.path.basename(source))[0]
    display_name = filename.replace("_", " ").replace("-", " ").strip()
    return display_name


# ==========================================
# 5. CLAUSE SPLITTER
# ==========================================
def split_into_clauses(raw_text):
    """
    Split ToS text into reasonably independent clauses.

    The Chrome extension often produces text with single-line breaks, so
    multiple parsing strategies are kept here.
    """
    text = raw_text.strip()
    if not text:
        return []

    # Normalize common web-extraction whitespace while preserving line breaks.
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[\t\f\v]+", " ", text)
    text = re.sub(r" +", " ", text)

    # Strategy 1: numbered headings / sections.
    numbered_split = re.split(
        r"\n(?=(?:\d+\.|\d+\.\d+|\d+\)|\bSECTION\s+\d+)\s+)",
        text,
        flags=re.IGNORECASE,
    )
    numbered_split = [c.strip() for c in numbered_split if c.strip()]
    if len(numbered_split) > 1:
        return numbered_split

    # Strategy 2: paragraph breaks.
    paragraph_split = [p.strip() for p in text.split("\n\n") if p.strip()]
    if len(paragraph_split) > 1:
        return paragraph_split

    # Strategy 3: single line breaks, common with extension extraction.
    line_split = [p.strip() for p in text.split("\n") if len(p.strip()) > 40]
    if len(line_split) > 1:
        return line_split

    # Strategy 4: character-based fallback.
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000,
        chunk_overlap=100,
    )
    chunks = text_splitter.split_text(text)
    return chunks if len(chunks) > 1 else [text]


# ==========================================
# 6. SEMANTIC RISK DETECTION
# ==========================================
RISK_CATEGORIES = [
    "data_privacy_risk",
    "liability_waiver",
    "retention_risk",
    "termination_risk",
    "consumer_financial_risk",
    "unilateral_modification_risk",
    "dispute_resolution_risk",
    "indemnification_risk",
    "ip_license_risk",
    "warranty_disclaimer_risk",
    "compliant",
]

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

_RISK_CLASSIFICATION_PROMPT = """You are a legal analyst reviewing ONE Terms of Service clause for potentially consumer-unfriendly terms.

Classify the clause into exactly ONE category below. Only flag a category when the clause
actually creates a meaningful consumer risk. Do not flag a clause merely because it contains
a related word such as "payment", "privacy", "termination", or "law".

Categories:

- data_privacy_risk: permits selling, sharing, profiling, tracking, or excessive collection
  of user data without clear consent or clear limits.

- liability_waiver: broadly disclaims the company's responsibility for security breaches,
  losses, damages, injury, negligence, or other harm that may reasonably be attributable
  to the company.

- retention_risk: permits indefinite or unnecessarily long retention of personal data, or
  continued use/sharing of personal data after account deletion or withdrawal of consent.

- termination_risk: permits suspension or termination at the company's sole discretion,
  especially without notice, reason, refund, or a meaningful appeal path.

- consumer_financial_risk: creates potentially unfair financial terms such as broad
  non-refundable policies, hidden fees, unexpected charges, automatic renewals without
  clear notice, difficult cancellation of paid services, or denial of reasonable refunds.

- unilateral_modification_risk: allows the company to change fees, material terms, or the
  agreement unilaterally with little/no notice or without giving the user a meaningful choice
  to cancel.

- dispute_resolution_risk: imposes potentially unfair dispute terms such as mandatory
  arbitration, class-action waiver, distant venue, or restrictions that materially limit
  practical access to remedies.

- indemnification_risk: requires the consumer to indemnify the company for unusually broad
  categories of claims, losses, or conduct, especially where the obligation is disproportionate
  to the user's control.

- ip_license_risk: grants the company an unusually broad, perpetual, irrevocable, transferable,
  sublicensable, or commercial license to user content beyond what is reasonably necessary to
  provide the service.

- warranty_disclaimer_risk: broadly states that the service is provided "as is" or disclaims
  important warranties, quality promises, or legal protections in a way that materially shifts
  ordinary service risk to the consumer.

- compliant: none of the above risks clearly apply.

Clause:
\"\"\"{clause}\"\"\"

Return category, confidence (0 to 1), concise reason, and an exact short excerpt from the
clause showing the key phrase."""

def classify_risk(clause_text):
    text = re.sub(
        r"^\d+\.\s+[A-Z][A-Z \-&]*\n",
        "",
        clause_text.strip(),
    )

    prompt = _RISK_CLASSIFICATION_PROMPT.format(clause=text[:2000])
    result = _call_gemini_json(prompt, _RISK_CLASSIFICATION_SCHEMA)

    return (
        result.get("category", "compliant"),
        float(result.get("confidence", 0.0)),
        result.get("reason", ""),
        result.get("excerpt", ""),
    )


# ==========================================
# 7. CONTRADICTION DETECTION
# ==========================================
# We no longer ask Gemini to compare an arbitrary sampled set of clauses.
# Instead, we use embeddings to find semantically related clauses and then
# ask Gemini to judge those candidate pairs. This preserves original clause
# numbers and prevents the old sampling/index-mapping bug.

_CONTRADICTION_SCHEMA = {
    "type": "object",
    "properties": {
        "contradictions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "pair_id": {"type": "integer"},
                    "excerpt_a": {"type": "string"},
                    "excerpt_b": {"type": "string"},
                    "explanation": {"type": "string"},
                },
                "required": [
                    "pair_id",
                    "excerpt_a",
                    "excerpt_b",
                    "explanation",
                ],
            },
        }
    },
    "required": ["contradictions"],
}

CONTRADICTION_EXACT_THRESHOLD_COUNT = 40
CONTRADICTION_TOP_NEIGHBORS = 6
CONTRADICTION_MAX_CANDIDATE_PAIRS = 120
CONTRADICTION_BATCH_SIZE = 12
CONTRADICTION_SIMILARITY_THRESHOLD = 0.34


def _cosine_similarity(a, b):
    """Cosine similarity for two embedding vectors."""
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))

    if norm_a == 0 or norm_b == 0:
        return 0.0

    return dot / (norm_a * norm_b)


def _build_contradiction_candidates(clauses):
    """
    Build candidate clause pairs.

    For small documents, compare every pair so we do not miss contradictions.
    For larger documents, use embeddings to keep only semantically related
    pairs. The original clause indexes are retained throughout.
    """
    n = len(clauses)
    if n < 2:
        return []

    # Small documents: exhaustive comparison is reliable and easy to reason about.
    if n <= CONTRADICTION_EXACT_THRESHOLD_COUNT:
        return [
            (i, j, clauses[i], clauses[j])
            for i in range(n)
            for j in range(i + 1, n)
        ]

    # Large documents: semantic candidate generation.
    print(f"Generating contradiction candidates for {n} clauses...")

    try:
        embeddings = law_embeddings.embed_documents(clauses)
    except Exception as e:
        print(f"Embedding candidate generation failed: {e}")
        # Safe fallback: compare adjacent/nearby clauses rather than sampling
        # arbitrary clauses and silently losing their original numbering.
        fallback = []
        window = min(10, n - 1)
        for i in range(n):
            for j in range(i + 1, min(n, i + window + 1)):
                fallback.append((i, j, clauses[i], clauses[j]))
        return fallback[:CONTRADICTION_MAX_CANDIDATE_PAIRS]

    pair_scores = []

    for i in range(n):
        neighbor_scores = []
        for j in range(n):
            if i == j:
                continue
            score = _cosine_similarity(embeddings[i], embeddings[j])
            neighbor_scores.append((score, j))

        neighbor_scores.sort(reverse=True, key=lambda x: x[0])

        for score, j in neighbor_scores[:CONTRADICTION_TOP_NEIGHBORS]:
            if j <= i:
                continue
            if score >= CONTRADICTION_SIMILARITY_THRESHOLD:
                pair_scores.append((score, i, j))

    # Remove duplicate pairs while preserving the strongest similarity score.
    unique_pairs = {}
    for score, i, j in pair_scores:
        key = (i, j)
        if key not in unique_pairs or score > unique_pairs[key]:
            unique_pairs[key] = score

    ranked_pairs = sorted(
        [(score, i, j) for (i, j), score in unique_pairs.items()],
        reverse=True,
    )

    ranked_pairs = ranked_pairs[:CONTRADICTION_MAX_CANDIDATE_PAIRS]

    return [
        (i, j, clauses[i], clauses[j])
        for _, i, j in ranked_pairs
    ]


def _judge_contradiction_batch(batch):
    """Ask Gemini to evaluate only a small batch of candidate pairs."""
    pair_blocks = []

    for local_pair_id, (original_i, original_j, clause_a, clause_b) in enumerate(
        batch,
        start=1,
    ):
        pair_blocks.append(
            f"""[PAIR {local_pair_id}]
CLAUSE A (original clause {original_i + 1}):
{clause_a}

CLAUSE B (original clause {original_j + 1}):
{clause_b}
"""
        )

    pair_text = "\n\n".join(pair_blocks)

    prompt = f"""You are a legal auditor reviewing candidate pairs from a Terms of Service agreement.

A contradiction means the two clauses create incompatible rules, promises, permissions,
rights, obligations, or restrictions when read together. Examples include:
- one clause says a user can cancel/refund while another says cancellation/refunds are impossible;
- one clause says data is deleted after account closure while another allows indefinite retention;
- one clause grants ownership/control while another takes away the same right;
- one clause promises a protection while another explicitly disclaims that protection.

Do NOT flag clauses merely because they discuss different aspects of the same topic.
Do NOT invent facts that are not present in the clauses.
Only return a contradiction when the two clauses genuinely conflict or materially undermine
one another.

Candidate pairs:
{pair_text}

Return the pair_id for every genuine contradiction. Use the PAIR number shown above.
For each contradiction, include short excerpts taken from the two clauses and a clear explanation."""

    try:
        return _call_gemini_json(prompt, _CONTRADICTION_SCHEMA)
    except Exception as e:
        print(f"Contradiction batch error: {e}")
        return {"contradictions": []}


def find_contradictions(clauses):
    """
    Detect contradictions without dropping or renumbering original clauses.

    Returns tuples:
        (original_clause_number_a, original_clause_number_b,
         excerpt_a, excerpt_b, explanation)
    """
    if len(clauses) < 2:
        return []

    candidates = _build_contradiction_candidates(clauses)
    if not candidates:
        return []

    contradictions = []

    # Keep a stable pair mapping for every batch so Gemini's pair_id can never
    # accidentally refer to the wrong original clause.
    for start in range(0, len(candidates), CONTRADICTION_BATCH_SIZE):
        batch = candidates[start:start + CONTRADICTION_BATCH_SIZE]
        result = _judge_contradiction_batch(batch)

        for pair in result.get("contradictions", []):
            local_pair_id = pair.get("pair_id")
            if local_pair_id is None:
                continue

            try:
                local_pair_id = int(local_pair_id)
            except (TypeError, ValueError):
                continue

            if not (1 <= local_pair_id <= len(batch)):
                continue

            original_i, original_j, clause_a, clause_b = batch[local_pair_id - 1]

            excerpt_a = (pair.get("excerpt_a") or clause_a[:400]).strip()
            excerpt_b = (pair.get("excerpt_b") or clause_b[:400]).strip()
            explanation = (
                pair.get("explanation")
                or "These two clauses appear to create an internal contradiction."
            ).strip()

            contradictions.append(
                (
                    original_i + 1,
                    original_j + 1,
                    excerpt_a,
                    excerpt_b,
                    explanation,
                )
            )

    # Deduplicate by original clause pair.
    deduped = []
    seen = set()

    for item in contradictions:
        a, b = item[0], item[1]
        key = tuple(sorted((a, b)))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)

    return deduped


# ==========================================
# 8. DOCUMENT SUMMARY
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
    if isinstance(raw_text, list):
        raw_text = " ".join(
            c.page_content if hasattr(c, "page_content") else str(c)
            for c in raw_text
        )

    text = raw_text.strip()
    if not text:
        return "No readable text was found in this document.", "low"

    prompt = f"""Summarize this Terms of Service in 3-4 sentences and rate overall risk as low, medium, or high:
\"\"\"{text[:6000]}\"\"\""""

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
    if isinstance(raw_text, list):
        raw_text = " ".join(
            c.page_content if hasattr(c, "page_content") else str(c)
            for c in raw_text
        )

    clauses = split_into_clauses(raw_text)
    findings = []

    print(f"Audit pipeline: {len(clauses)} clauses detected.")

    # Pass 1: semantic risk classification.
    for clause_number, clause in enumerate(clauses, start=1):
        try:
            risk_category, score, reason, excerpt = classify_risk(clause)
        except Exception as e:
            print(f"Risk classification failed for clause {clause_number}: {e}")
            continue

        if risk_category != "compliant":
            try:
                matching_laws = search_indian_laws(clause)
            except Exception as e:
                print(f"Law search failed for clause {clause_number}: {e}")
                matching_laws = []

            # Fallback citation so risky clauses are never dropped.
            if matching_laws:
                citation = format_citation(matching_laws[0])
                law_excerpt = matching_laws[0].page_content[:200].strip() + "..."
            else:
                fallback_citations = {
                    "data_privacy_risk": "General Data Privacy Risk",
                    "liability_waiver": "General Liability & Consumer Protection Risk",
                    "retention_risk": "General Data Retention Risk",
                    "termination_risk": "General Account Termination Risk",
                    "consumer_financial_risk": "General Consumer Financial / Refund Risk",
                    "unilateral_modification_risk": "General Contract Modification Risk",
                    "dispute_resolution_risk": "General Consumer Dispute Resolution Risk",
                    "indemnification_risk": "General Consumer Indemnification Risk",
                    "ip_license_risk": "General User Content / IP Licensing Risk",
                    "warranty_disclaimer_risk": "General Warranty / Consumer Protection Risk",
                }
                citation = fallback_citations.get(
                    risk_category, "General Consumer Protection Risk"
                )
                law_excerpt = (
                    "Flagged potentially unfair consumer practice; no direct statutory match "
                    "was found in the local law database."
                )

            findings.append(
                {
                    "clause_number": clause_number,
                    "clause_text": excerpt if excerpt else clause,
                    "risk_category": "high_risk",
                    "risk_type": risk_category,
                    "explanation": (
                        f"{reason} (confidence {score:.2f})"
                        if reason
                        else f"Detected: {risk_category.replace('_', ' ')} "
                             f"(confidence {score:.2f})"
                    ),
                    "legal_citation": citation,
                    "law_excerpt": law_excerpt,
                }
            )

    # Pass 2: contradiction detection over original clause numbers.
    print("Checking for internal contradictions...")
    all_pairs = find_contradictions(clauses)

    for clause_num_a, clause_num_b, excerpt_a, excerpt_b, explanation in all_pairs:
        findings.append(
            {
                "clause_number": f"{clause_num_a} & {clause_num_b}",
                "clause_text": f"{excerpt_a}\n\n—vs—\n\n{excerpt_b}",
                "risk_category": "contradiction",
                "explanation": explanation,
                "legal_citation": "Internal inconsistency — flagged for manual review",
                "law_excerpt": "",
            }
        )

    print(f"Audit complete: {len(findings)} total findings, {len(all_pairs)} contradictions.")
    return findings


# ==========================================
# 10. RESPONSE FORMATTER FOR CHROME EXTENSION
# ==========================================
def format_extension_response(summary_text: str, overall_risk: str, findings: list):
    contradictions = []
    risky_clauses = []

    for f in findings:
        if f.get("risk_category") == "contradiction":
            clauses = f.get("clause_text", "").split("\n\n—vs—\n\n")
            clause_1 = clauses[0] if len(clauses) > 0 else ""
            clause_2 = clauses[1] if len(clauses) > 1 else ""

            contradictions.append(
                {
                    "clause_1": clause_1,
                    "clause_2": clause_2,
                    "clause_number": f.get("clause_number", "?"),
                    "explanation": f.get("explanation", ""),
                }
            )
        else:
            risky_clauses.append(
                {
                    "category": f.get("risk_type", "risk"),
                    "clause_text": f.get("clause_text", ""),
                    "explanation": f.get("explanation", ""),
                    "legal_citation": f.get("legal_citation", ""),
                    "clause_number": f.get("clause_number", "?"),
                }
            )

    risk_level = (overall_risk or "medium").upper()

    if risk_level == "HIGH":
        score = min(10, 7 + len(risky_clauses) + len(contradictions))
        suggestion = (
            "Exercise extreme caution. Consider negotiating terms or seeking alternatives."
        )
    elif risk_level == "MEDIUM":
        score = min(8, 4 + len(risky_clauses) + len(contradictions))
        suggestion = (
            "Review data privacy and liability waivers carefully before accepting."
        )
    else:
        score = max(1, 1 + len(risky_clauses) + len(contradictions))
        suggestion = "Standard terms overall, but review flagged items below."

    # Keep the original Chrome-extension fields AND provide findings for
    # the Streamlit client so both clients consume the same backend result.
    return {
        "risk_score": score,
        "risk_level": risk_level,
        "summary": summary_text,
        "suggestion": suggestion,
        "contradictions": contradictions,
        "risky_clauses": risky_clauses,
        "findings": findings,
    }


# ==========================================
# 11. FASTAPI APPLICATION & ENDPOINTS
# ==========================================
app = FastAPI(title="ToS Auditor")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def check_kitchen_status():
    return {"message": "Hello! The Kitchen Drive-Thru is OPEN!"}


def _extract_text_from_chunks(chunks):
    return " ".join(c.page_content for c in chunks)


@app.post("/audit-text/")
def audit_pasted_text(raw_text: str = Form(...)):
    summary_text, overall_risk = summarize_document(raw_text)
    findings = audit_text(raw_text)
    return format_extension_response(summary_text, overall_risk, findings)


@app.post("/audit-file/")
def audit_uploaded_file(file: UploadFile = File(...)):
    safe_name = os.path.basename(file.filename or "")
    if not safe_name:
        return {"error": "Invalid file name."}

    temp_filepath = os.path.join(UPLOAD_FOLDER, safe_name)
    name_lower = safe_name.lower()

    try:
        with open(temp_filepath, "wb") as f:
            f.write(file.file.read())

        if name_lower.endswith(".pdf"):
            text_to_audit = _extract_text_from_chunks(process_pdf(temp_filepath))
        elif name_lower.endswith((".png", ".jpg", ".jpeg")):
            text_to_audit = process_image(temp_filepath)
        elif name_lower.endswith(".docx"):
            text_to_audit = _extract_text_from_chunks(process_docx(temp_filepath))
        else:
            return {"error": "Sorry, we don't cook this type of file!"}

    finally:
        if os.path.exists(temp_filepath):
            os.remove(temp_filepath)

    summary_text, overall_risk = summarize_document(text_to_audit)
    findings = audit_text(text_to_audit)

    return format_extension_response(summary_text, overall_risk, findings)


# ==========================================
# 12. LOCAL SERVER ENTRY POINT
# ==========================================
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)
