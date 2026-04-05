# app.py
from langchain_community.document_loaders import PyPDFLoader
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS

def main():
    print("🧠 1. Waking up the AI Brain (Loading The Reference)...")

    # Load the same embeddings model
    embeddings = HuggingFaceEmbeddings(
        model_name="sentence-transformers/all-MiniLM-L6-v2"
    )

    # Load the FAISS database we built
    vector_db = FAISS.load_local(
        "./faiss_db",        # ← matches document_processor.py
        embeddings,
        allow_dangerous_deserialization=True
    )
    print("✅ Indian Laws successfully loaded from memory!")

    print("\n📄 2. Loading the ToS (The Target)...")
    # Change "sample.pdf" to your ToS PDF name
    loader = PyPDFLoader("sample.pdf")
    tos_pages = loader.load()
    print(f"✅ Successfully read {len(tos_pages)} pages of the Terms of Service.")

    print("\n🚀 Both Target and Reference are ready for auditing!")
    

if __name__ == "__main__":
    main()