from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter

# 1. Load the PDF
print("Reading the PDF...")
loader = PyPDFLoader("sample.pdf")
pages = loader.load()

# 2. Chunking (Splitting the text into small pieces)
print("Chopping text into bite-sized chunks...")
text_splitter = RecursiveCharacterTextSplitter(
    chunk_size=1000, 
    chunk_overlap=100
)
chunks = text_splitter.split_documents(pages)

# 3. Final Success Message
print(f"DONE! I read {len(pages)} pages and chopped them into {len(chunks)} small chunks.")
# 2. Show the result