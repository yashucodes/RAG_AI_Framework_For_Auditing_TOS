# app.py (The Kitchen / Backend)
from langchain_community.document_loaders import PyPDFLoader, Docx2txtLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.documents import Document # Helps package pasted text!
from PIL import Image          
import pytesseract             

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
if __name__ == "__main__":
    print("\n--- Running Local Test ---")
    try:
        # Testing your old sample.pdf exactly how you had it!
        test_chunks = process_pdf("sample.pdf")
        print("Success! The app.py backend is working perfectly on its own.")
    except Exception as e:
        print(f"Could not test sample.pdf. Make sure the file exists! Error: {e}")