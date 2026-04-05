# document_processor.py
import os
import shutil
from langchain_community.document_loaders import PyPDFDirectoryLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS

def train_model():
    print("1. Looking for PDF files in dataset folder...")
    try:
        loader = PyPDFDirectoryLoader("dataset")
        documents = loader.load()
        print(f"Successfully read {len(documents)} pages!")
    except Exception as e:
        print(f"Error reading PDFs: {e}")
        return

    print("2. Chopping text into small pieces...")
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000,
        chunk_overlap=100
    )
    chunks = text_splitter.split_documents(documents)
    print(f"Created {len(chunks)} chunks!")

    print("3. Loading AI embeddings...")
    embeddings = HuggingFaceEmbeddings(
        model_name="sentence-transformers/all-MiniLM-L6-v2"
    )

    print("4. Building FAISS vector database...")
    vector_db = FAISS.from_documents(chunks, embeddings)

    # Save the database
    vector_db.save_local("./faiss_db")
    print("SUCCESS! Indian Laws stored as vectors and ready!")

if __name__ == "__main__":
    train_model()