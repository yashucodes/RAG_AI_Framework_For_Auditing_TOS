# app.py (The Kitchen / Backend)
from langchain_community.document_loaders import PyPDFLoader, Docx2txtLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.documents import Document # Helps package pasted text!
from PIL import Image          
import pytesseract 
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS            

# --- SETUP ROBOT EYES ---
pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

# ==========================================
# 1. PDF RECIPE
# ==========================================
def process_pdf(file_path):
    print(f"Reading the PDF from {file_path}...")
    loader = PyPDFLoader(file_path)
    pages = loader.load()
    
    print("Chopping text into bite-sized chunks...")
    text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=100)
    chunks = text_splitter.split_documents(pages)
    
    # Brought over from your old code!
    print(f"DONE! I read {len(pages)} pages and chopped them into {len(chunks)} small chunks.")
    return chunks

# ==========================================
# 2. IMAGE RECIPE
# ==========================================
def process_image(file_path):
    print(f"Opening image from {file_path}...")
    my_picture = Image.open(file_path)
    return pytesseract.image_to_string(my_picture)

# ==========================================
# 3. WORD DOC RECIPE
# ==========================================
def process_docx(file_path):
    print(f"Reading Word Doc from {file_path}...")
    loader = Docx2txtLoader(file_path)
    pages = loader.load()
    
    print("Chopping text into bite-sized chunks...")
    text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=100)
    chunks = text_splitter.split_documents(pages)
    return chunks

# ==========================================
# 4. PASTED TEXT RECIPE
# ==========================================
def process_text(raw_text):
    print("Reading pasted text...")
    # We have to wrap raw text in a "Document" so LangChain knows how to chop it
    doc = [Document(page_content=raw_text)]
    text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=100)
    return text_splitter.split_documents(doc)


# ==========================================
# LOCAL TESTING (Brought over from old code)
# ==========================================
# This block ONLY runs if you type `python app.py` in the terminal.
# It will NOT run when frontend.py calls these functions!


# ==========================================
# 5. THE WALKIE-TALKIE (SEARCH DATABASE)
# ==========================================
from sentence_transformers import CrossEncoder

# Load once at module level so it doesn't reload on every search call
reranker = CrossEncoder('cross-encoder/ms-marco-MiniLM-L-6-v2')

# --- TUNE THESE TWO NUMBERS AFTER TESTING ---
FAISS_DISTANCE_THRESHOLD = 1.5   # lower = stricter. FAISS L2 distance: lower = more similar
CROSSENCODER_SCORE_THRESHOLD = -2.0  # higher = stricter. Typical range: -10 to +10


def search_indian_laws(query_text):
    print(f"Searching Archive for: '{query_text[:50]}...'")

    embeddings = HuggingFaceEmbeddings(
        model_name="sentence-transformers/all-MiniLM-L6-v2"
    )

    vector_db = FAISS.load_local(
        "./faiss_db",
        embeddings,
        allow_dangerous_deserialization=True
    )

    # STAGE 1: Bi-encoder retrieval (fast, rough)
    # similarity_search_with_score returns (doc, distance) — lower distance = closer match
    candidates = vector_db.similarity_search_with_score(query_text, k=10)

    # Filter out anything too far away before we even bother reranking
    filtered_candidates = [
        (doc, score) for doc, score in candidates
        if score <= FAISS_DISTANCE_THRESHOLD
    ]

    if not filtered_candidates:
        print("No candidates passed the FAISS distance threshold.")
        return []

    # STAGE 2: Cross-encoder reranking (slow, accurate)
    pairs = [(query_text, doc.page_content) for doc, _ in filtered_candidates]
    rerank_scores = reranker.predict(pairs)

    # Attach cross-encoder scores and filter again
    scored_results = [
        (doc, ce_score)
        for (doc, _), ce_score in zip(filtered_candidates, rerank_scores)
        if ce_score >= CROSSENCODER_SCORE_THRESHOLD
    ]

    # Sort by cross-encoder score, best first
    scored_results.sort(key=lambda x: x[1], reverse=True)

    if not scored_results:
        print("No candidates passed the cross-encoder relevance check.")
        return []

    # Return top 3 relevant laws (just the documents, matching your original return type)
    matching_laws = [doc for doc, score in scored_results[:3]]
    return matching_laws


if __name__ == "__main__":
    print("\n--- Running Local Test ---")
    try:
        # Testing your old sample.pdf exactly how you had it!
        test_chunks = process_pdf("sample.pdf")
        print("Success! The app.py backend is working perfectly on its own.")
    except Exception as e:
        print(f"Could not test sample.pdf. Make sure the file exists! Error: {e}")