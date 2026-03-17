import streamlit as st
import os
import tempfile
from backend import process_resume

st.set_page_config(page_title="AI Resume Parser", layout="centered")

st.title("📄 AI Resume Parser")
st.write("Upload your resume and get a structured version instantly.")

st.warning("⚠️ Note: Resumes containing images are NOT supported yet. This will be available in the next release.")

uploaded_file = st.file_uploader("Upload Resume (PDF only)", type=["pdf"])

TEMPLATE_PATH = "resume_template_sample.docx"

if uploaded_file is not None:
    st.success("✅ File uploaded successfully!")

    if st.button("Generate Resume"):
        with st.spinner("Processing your resume..."):
            with tempfile.TemporaryDirectory() as tmpdir:
                pdf_path = os.path.join(tmpdir, uploaded_file.name)
                output_path = os.path.join(tmpdir, "generated_resume.docx")

                with open(pdf_path, "wb") as f:
                    f.write(uploaded_file.read())

                try:
                    process_resume(pdf_path, TEMPLATE_PATH, output_path)

                    with open(output_path, "rb") as f:
                        docx_bytes = f.read()

                    st.download_button(
                        label="⬇️ Download Generated Resume",
                        data=docx_bytes,
                        file_name="generated_resume.docx",
                        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                    )

                except Exception as e:
                    st.error(f"Error processing resume: {str(e)}")