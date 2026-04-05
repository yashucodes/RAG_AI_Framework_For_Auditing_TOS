# frontend.py
import streamlit as st
import os 
from app import process_pdf, process_image, process_docx, process_text, search_indian_laws  

st.set_page_config(page_title="ToS Auditor", page_icon="⚖️")
st.title("⚖️ Legal ToS Auditor")

UPLOAD_FOLDER = "temp_uploads"
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

tab1, tab2 = st.tabs(["📁 Upload Document", "📝 Paste Text"])

# ==========================================
# TAB 1: THE UPLOAD BASKET
# ==========================================
with tab1:
    uploaded_files = st.file_uploader(
        "Upload your ToS documents (PDF, DOCX, or Images!)", 
        type=["pdf", "png", "jpg", "jpeg", "docx"],
        accept_multiple_files=True
    )

    if uploaded_files: 
        st.success(f"Uploaded {len(uploaded_files)} file(s).")
        
        if st.button("Start Audit on Files"):
            for uploaded_file in uploaded_files:
                st.write(f"**Reading:** {uploaded_file.name}...")

                temp_filepath = os.path.join(UPLOAD_FOLDER, uploaded_file.name)
                with open(temp_filepath, "wb") as f:
                    f.write(uploaded_file.read())
                
                # We will store the text here so we can search it later!
                text_to_search = ""
                
                # 1. PROCESS THE FILE BASED ON ITS TYPE
                if uploaded_file.name.lower().endswith(".pdf"):
                    chopped_chunks = process_pdf(temp_filepath)
                    st.success(f"👨‍🍳 PDF chopped into {len(chopped_chunks)} pieces!")
                    text_to_search = chopped_chunks[0].page_content
                    
                elif uploaded_file.name.lower().endswith((".png", ".jpg", ".jpeg")):
                    extracted_text = process_image(temp_filepath)
                    st.success(f"👁️ Success! Found text in your image!")
                    text_to_search = extracted_text 
                    
                elif uploaded_file.name.lower().endswith(".docx"):
                    chopped_chunks = process_docx(temp_filepath)
                    st.success(f"📝 Word Doc chopped into {len(chopped_chunks)} pieces!")
                    text_to_search = chopped_chunks[0].page_content

                # 2. SEARCH THE DATABASE (Runs for ALL files now!)
                st.write("🔍 Asking the Librarian for matching laws...")
                matching_laws = search_indian_laws(text_to_search)
                
                st.success("📚 Found matching legal context!")
                st.write("**Here is the most relevant law it found:**")
                st.info(matching_laws[0].page_content)

# ==========================================
# TAB 2: THE COPY-PASTE BOX
# ==========================================
with tab2:
    st.write("Don't have a file? Just copy and paste the legal text below.")
    pasted_text = st.text_area("Paste Terms of Service here:", height=300)
    
    if pasted_text:
        if st.button("Start Audit on Pasted Text"):
            st.success("Text received successfully!")
            st.write("🔧 Handing pasted text to the Kitchen...")
            
            # 1. PROCESS TEXT
            chopped_chunks = process_text(pasted_text)
            st.success(f"👨‍🍳 Pasted text chopped into {len(chopped_chunks)} pieces!")
            
            # 2. SEARCH THE DATABASE
            st.write("🔍 Asking the Librarian for matching laws...")
            matching_laws = search_indian_laws(chopped_chunks[0].page_content)
            
            st.success("📚 Found matching legal context!")
            st.write("**Here is the most relevant law it found:**")
            st.info(matching_laws[0].page_content)