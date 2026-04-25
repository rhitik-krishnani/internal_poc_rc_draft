import streamlit as st
import os
import tempfile
from backend import process_resume

st.set_page_config(page_title="AI Resume Parser", layout="centered")

st.title("AI Resume Parser")

uploaded_file = st.file_uploader("Upload Resume (PDF)", type=["pdf"])

TEMPLATE_PATH = "resume_template_sample.docx"

if uploaded_file:
    if st.button("Generate Resume"):
        with st.spinner("Processing..."):
            with tempfile.TemporaryDirectory() as tmpdir:
                pdf_path = os.path.join(tmpdir, uploaded_file.name)
                output_path = os.path.join(tmpdir, "generated_resume.docx")

                with open(pdf_path, "wb") as f:
                    f.write(uploaded_file.read())

                try:
                    process_resume(pdf_path, TEMPLATE_PATH, output_path)

                    with open(output_path, "rb") as f:
                        st.download_button(
                            label="Download Resume",
                            data=f,
                            file_name="generated_resume.docx",
                            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                        )

                except Exception as e:
                    st.error(str(e))
