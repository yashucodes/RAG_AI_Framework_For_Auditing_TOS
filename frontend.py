# frontend.py
import streamlit as st
import os
from app import process_pdf, process_image, process_docx, process_text, search_indian_laws

st.set_page_config(page_title="ToS Auditor", page_icon="⚖️")
st.title("⚖️ Legal ToS Auditor")

UPLOAD_FOLDER = "temp_uploads"
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)


def display_results(matching_laws):
    """Shows the top matching law, or a clear message if nothing relevant was found."""
    if not matching_laws:
        st.warning("⚠️ No relevant legal provision found for this text.")
    else:
        st.write("**Most relevant law found:**")
        st.info(matching_laws[0].page_content)


tab1, tab2 = st.tabs(["📁 Upload Document", "📝 Paste Text"])

# ==========================================
# TAB 1: UPLOAD
# ==========================================
with tab1:
    uploaded_files = st.file_uploader(
        "Upload your ToS documents (PDF, DOCX, or Images)",
        type=["pdf", "png", "jpg", "jpeg", "docx"],
        accept_multiple_files=True
    )

    if uploaded_files:
        st.success(f"Uploaded {len(uploaded_files)} file(s).")

        if st.button("Start Audit on Files"):
            for uploaded_file in uploaded_files:
                st.write(f"**Processing:** {uploaded_file.name}")

                temp_filepath = os.path.join(UPLOAD_FOLDER, uploaded_file.name)
                with open(temp_filepath, "wb") as f:
                    f.write(uploaded_file.read())

                text_to_search = ""
                name_lower = uploaded_file.name.lower()

                if name_lower.endswith(".pdf"):
                    chopped_chunks = process_pdf(temp_filepath)
                    text_to_search = chopped_chunks[0].page_content

                elif name_lower.endswith((".png", ".jpg", ".jpeg")):
                    text_to_search = process_image(temp_filepath)

                elif name_lower.endswith(".docx"):
                    chopped_chunks = process_docx(temp_filepath)
                    text_to_search = chopped_chunks[0].page_content

                matching_laws = search_indian_laws(text_to_search)
                display_results(matching_laws)

# ==========================================
# TAB 2: PASTE TEXT
# ==========================================
with tab2:
    pasted_text = st.text_area("Paste Terms of Service here:", height=300)

    if pasted_text:
        if st.button("Start Audit on Pasted Text"):
            chopped_chunks = process_text(pasted_text)
            matching_laws = search_indian_laws(chopped_chunks[0].page_content)
            display_results(matching_laws)