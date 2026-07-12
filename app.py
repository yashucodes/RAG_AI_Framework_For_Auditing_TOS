# app.py (The Kitchen / Backend)
import os
from fastapi import FastAPI, UploadFile, File, Form
from langchain_community.document_loaders import PyPDFLoader, Docx2txtLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.documents import Document # Helps package pasted text!
from PIL import Image          
import pytesseract 
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS            
from sentence_transformers import CrossEncoder

# --- SETUP ROBOT EYES ---
pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

# Load once at module level so it doesn't reload on every search call
reranker = CrossEncoder('cross-encoder/ms-marco-MiniLM-L-6-v2')

# --- TUNE THESE TWO NUMBERS AFTER TESTING ---
FAISS_DISTANCE_THRESHOLD = 1.4  # lower = stricter. FAISS L2 distance: lower = more similar
CROSSENCODER_SCORE_THRESHOLD = -7.0  # higher = stricter. Typical range: -10 to +10

# ==========================================
# RECIPES (Chop the food)
# ==========================================
def process_pdf(file_path):
    loader = PyPDFLoader(file_path)
    pages = loader.load()
    text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=100)
    return text_splitter.split_documents(pages)

def process_image(file_path):
    my_picture = Image.open(file_path)
    raw_text = pytesseract.image_to_string(my_picture)
    
    # FIX: We wrapped the text in a Document and gave it the knife!
    doc = [Document(page_content=raw_text)]
    text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=100)
    return text_splitter.split_documents(doc)

def process_docx(file_path):
    loader = Docx2txtLoader(file_path)
    pages = loader.load()
    text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=100)
    return text_splitter.split_documents(pages)

def process_text(raw_text):
    doc = [Document(page_content=raw_text)]
    text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=100)
    return text_splitter.split_documents(doc)

# ==========================================
# THE WALKIE-TALKIE (SEARCH DATABASE)
# ==========================================
def search_indian_laws(query_text):
    embeddings = HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")
    vector_db = FAISS.load_local("./faiss_db", embeddings, allow_dangerous_deserialization=True)

    candidates = vector_db.similarity_search_with_score(query_text, k=10)
    filtered_candidates = [(doc, score) for doc, score in candidates if score <= FAISS_DISTANCE_THRESHOLD]

    if not filtered_candidates:
        return []

    pairs = [(query_text, doc.page_content) for doc, _ in filtered_candidates]
    rerank_scores = reranker.predict(pairs)

    scored_results = [
        (doc, ce_score) for (doc, _), ce_score in zip(filtered_candidates, rerank_scores)
        if ce_score >= CROSSENCODER_SCORE_THRESHOLD
    ]
    scored_results.sort(key=lambda x: x[1], reverse=True)

    if not scored_results:
        return []

    return [doc for doc, score in scored_results[:3]]

# ==========================================
# THE DRIVE-THRU WINDOWS (FastAPI)
# ==========================================
app = FastAPI(title="ToS Auditor Kitchen")

@app.get("/")
def check_kitchen_status():
    return {"message": "Hello! The Kitchen Drive-Thru is OPEN!"}

# Window 1: For Pasted Text
@app.post("/audit-text/")
def audit_pasted_text(raw_text: str = Form(...)):
    chunks = process_text(raw_text)
    matching_laws = search_indian_laws(chunks[0].page_content)
    
    # We send the answers out the window in a neat little dictionary box
    return {
        "chunks_count": len(chunks),
        "matched_laws": [law.page_content for law in matching_laws]
    }
# Window 2: For Uploaded Files (PDFs, Images, Word Docs)
@app.post("/audit-file/")
def audit_uploaded_file(file: UploadFile = File(...)):
    print(f"Drive-Thru received a file: {file.filename}")
    
    # 1. Put the file on the counter (save it temporarily)
    temp_filepath = f"temp_uploads/{file.filename}"
    with open(temp_filepath, "wb") as f:
        f.write(file.file.read())
    
    # 2. Look at the file and use the right recipe!
    if file.filename.lower().endswith(".pdf"):
        chunks = process_pdf(temp_filepath)
    elif file.filename.lower().endswith((".png", ".jpg", ".jpeg")):
        chunks = process_image(temp_filepath)
    elif file.filename.lower().endswith(".docx"):
        chunks = process_docx(temp_filepath)
    else:
        return {"error": "Sorry, we don't cook this type of file!"}
        
    # 3. Clean up the counter (delete the temp file)
    os.remove(temp_filepath)
    
    # 4. Use the Walkie-Talkie to get the laws
    matching_laws = search_indian_laws(chunks[0].page_content)
    
    # 5. Slide the meal back out the window!
    return {
        "chunks_count": len(chunks),
        "matched_laws": [law.page_content for law in matching_laws]
    }