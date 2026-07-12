# frontend.py
import streamlit as st
import requests

st.set_page_config(page_title="ToS Auditor", page_icon="⚖️")
st.title("⚖️ Legal ToS Auditor")

# The URL address of our FastAPI backend window
BACKEND_URL = "http://127.0.0.1:8000"

def display_results(matching_laws):
    """Shows the top matching law, or a clear message if nothing relevant was found."""
    if not matching_laws:
        st.warning("⚠️ No relevant legal provision found for this text.")
    else:
        st.write("**Most relevant law found:**")
        # FastAPI returns a list of simple strings now, so no need for .page_content here!
        st.info(matching_laws[0])

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
                st.write(f"**Processing:** {uploaded_file.name} via Backend...")
                
                # Package the file to send over the web to the FastAPI Drive-Thru
                files = {"file": (uploaded_file.name, uploaded_file.getvalue(), uploaded_file.type)}
                
                try:
                    # Send it to Window 2!
                    response = requests.post(f"{BACKEND_URL}/audit-file/", files=files)
                    
                    if response.status_code == 200:
                        result = response.json()
                        if "error" in result:
                            st.error(result["error"])
                        else:
                            st.success(f"👨‍🍳 Backend chopped file into {result['chunks_count']} pieces!")
                            display_results(result.get("matched_laws", []))
                    else:
                        st.error(f"Oops! The backend encountered an error. Status code: {response.status_code}")
                        
                except requests.exceptions.ConnectionError:
                    st.error("🚨 Could not connect to backend. Is the Uvicorn server running?")

# ==========================================
# TAB 2: PASTE TEXT
# ==========================================
with tab2:
    pasted_text = st.text_area("Paste Terms of Service here:", height=300)

    if pasted_text:
        if st.button("Start Audit on Pasted Text"):
            st.write("Sending text to Backend...")
            
            # Package the text data
            data = {"raw_text": pasted_text}
            
            try:
                # Send it to Window 1!
                response = requests.post(f"{BACKEND_URL}/audit-text/", data=data)
                
                if response.status_code == 200:
                    result = response.json()
                    st.success(f"👨‍🍳 Backend chopped pasted text into {result['chunks_count']} pieces!")
                    display_results(result.get("matched_laws", []))
                else:
                    st.error(f"Oops! The backend encountered an error. Status code: {response.status_code}")
                    
            except requests.exceptions.ConnectionError:
                st.error("🚨 Could not connect to backend. Is the Uvicorn server running?")