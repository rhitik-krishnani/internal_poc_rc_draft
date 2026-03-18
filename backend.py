import json
import random
from textwrap import dedent
from fastapi import HTTPException
import docx
from docx.shared import RGBColor
from docx import Document
from datetime import datetime
import os
from docx.shared import Pt
from docx.enum.text import WD_ALIGN_PARAGRAPH
import pdfplumber
import requests
import re
import ast
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.text.paragraph import Paragraph


def extract_resume_text(pdf_path: str) -> str:
    text = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text()
            if page_text:
                text.append(page_text)
    return "\n".join(text)


template_sample = {
    "1": "Name",
    "2": "Designtation or Current Job Title",
    "3": "Professional Summary capturing overall journey in 4-5 lines",
    "4": "Primary Tools",
    "5": "Cloud & Infrastructure: ",
    "6": "Other Skills",
    "7": "Professional Experience",
    "8": "Certifications"
}


def get_prompt_for_resume_template_fill(resume_text, template_sample):

    system_prompt = """
You are an expert resume parsing and structured information extraction system.

Your task is to extract information from the provided resume and populate the template.

### RULES ###
1. Use ONLY information explicitly present in the resume.
2. Do NOT invent or infer any information.
3. Do NOT create new fields.
4. Do NOT modify tag numbers.
5. Do NOT skip any tag.
6. Preserve factual accuracy.
"""

    user_prompt = f"""
Extract information from the resume and populate each tag as per the instructions below.

### RESUME RAW TEXT ###
{resume_text}

### TEMPLATE STRUCTURE ###
{template_sample}

### INSTRUCTIONS ###

1. Read the template carefully and identify each numbered tag.
2. Extract the relevant information from the resume for each tag.
3. Return the answer inside the SAME tag number.
4. Do NOT change tag numbers.
5. Do NOT change tag order.
6. If information for a tag is not available in the resume, leave the tag empty.

### PROFESSIONAL EXPERIENCE — STRICT FORMATTING RULES ###

RULE 1 — COMPANY NAME:
- Print the company name ONLY ONCE — at the very top, before any roles.
- Do NOT repeat the company name for subsequent roles under the same company.

RULE 2 — STRUCTURE ORDER (always follow this exact order):
  1. Company name + timeline
  2. Role title
  3. Projects under that role (if any)
  4. (blank line)
  5. Next role title (if same company)
  6. Projects under that role (if any)
  7. (blank line)
  8. Next company name + timeline (if different company) and so on.

** NOTE - 
- Timeline will ONLY be mentioned for the Company Name in the Ouput.
- ENSURE wherever you provide timeline, the format should Timeline mmm-yy like Jan 26 - Oct 25 or Jan-25 - present whichever is applicable. Do not provide tenure anywhere.

RULE 3 — WRAPPING (CRITICAL TO FOLLOW):
- Wrap Company Name and Timeline inside <b> tags.
- Wrap every Role title inside <b> tags. Do NOT include timeline, duration, or pipe symbol (|) in role tags.
- Wrap every Project name inside <b> tags. Do NOT include timeline, duration, or pipe symbol (|) in project tags.

RULE 4 — MANDATORY EXAMPLE (follow this exact pattern):

Single role at a company:
<b> Company ABC (Jan 2018 - Dec 2019) </b>
<b> Software Engineer </b>
<b> Project: Project Alpha </b>
• Responsibility 1
• Responsibility 2
• Responsibility 3.... and so on.
<b> Project: Project Beta </b>
• Responsibility 1
• Responsibility 2
• Responsibility 3.... and so on.
Multiple roles at the same company (company name appears ONLY ONCE):
<b> Company XYZ (Mar 2020 - Present) </b>

<b> Senior Engineer </b>
<b> Project: Project Gamma </b>
• Responsibility 1
• Responsibility 2
• Responsibility 3.... and so on.
<b> Project: Project Delta </b>
• Responsibility 1
• Responsibility 2
• Responsibility 3.... and so on.

<b> Junior Engineer </b>
<b> Project: Project Epsilon </b>
• Responsibility 1
• Responsibility 2
• Responsibility 3.... and so on.

Multiple companies (repeat full structure per company):
<b> Company XYZ (Mar 2020 - Present) </b>

<b> Senior Engineer </b>
<b> Project: Project Gamma </b>
• Responsibility 1
• Responsibility 2
• Responsibility 3.... and so on.

<b> Company ABC (Jan 2018 - Feb 2020) </b>

<b> Analyst </b>
<b> Project: Project Zeta </b>
• Responsibility 1
• Responsibility 2
• Responsibility 3.... and so on.

- ENSURE NOT to deviate from this structure under any circumstances, else you will be penalized heavily.

### CERTIFICATIONS — STRICT RULES ###

- If certifications are present in the resume, populate the certification tags normally.
- Each unique certification must be on a new line
  - Example:
    • Certification 1
    • Certification 2
    • Certification 3.... and so on.
- If NO certifications are found, return exactly: <missing_certification></missing_certification>
- Do NOT invent or infer certifications.

### STRICT OUTPUT RULES ###

- Output must contain ONLY the filled tags.
- Do NOT include explanations.
- Do NOT include markdown formatting.
- Do NOT add any text outside the tags.
- Do NOT repeat instructions in output.
- Return the fully filled template.
- Return valid JSON only.
"""

    return system_prompt, user_prompt


import os
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

HF_API_KEY = st.secrets.get("HF_API_KEY") or os.getenv("HF_API_KEY")

MODEL = "Qwen/Qwen2.5-72B-Instruct"
API_URL = f"https://router.huggingface.co/v1/chat/completions"

headers = {
    "Authorization": f"Bearer {HF_API_KEY}",
    "Content-Type": "application/json"
}


def narrate(system_prompt, user_prompt):
    try:
        payload = {
            "model": MODEL,
            "messages": [
                {"role": "system", "content": dedent(system_prompt).strip()},
                {"role": "user", "content": user_prompt}
            ],
            "temperature": 0.0,
            "max_tokens": 1024
        }

        response = requests.post(API_URL, headers=headers, json=payload, timeout=60)

        if response.status_code != 200:
            raise Exception(response.text)

        result = response.json()
        return result["choices"][0]["message"]["content"].strip()

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI model error: {str(e)}")


def safe_parse(response: str):
    try:
        cleaned = response.strip()
        cleaned = re.sub(r'^```json\s*', '', cleaned)
        cleaned = re.sub(r'^```\s*', '', cleaned)
        cleaned = re.sub(r'\s*```$', '', cleaned)

        try:
            return json.loads(cleaned)
        except Exception:
            pass

        try:
            return ast.literal_eval(cleaned)
        except Exception:
            pass

        cleaned_fixed = cleaned.replace('\n', ' ')
        return json.loads(cleaned_fixed)

    except Exception as e:
        raise ValueError(f"Parsing failed: {e}")


def is_valid_json(data):
    if isinstance(data, dict):
        return True
    if isinstance(data, str):
        try:
            json.loads(data)
            return True
        except json.JSONDecodeError:
            return False
    return False


def _add_right_tab_stop(paragraph, position_twips=9000):
    p = paragraph._p
    pPr = p.get_or_add_pPr()
    tabs = pPr.find(qn("w:tabs"))
    if tabs is None:
        tabs = OxmlElement("w:tabs")
        pPr.append(tabs)
    tab = OxmlElement("w:tab")
    tab.set(qn("w:val"), "right")
    tab.set(qn("w:pos"), str(position_twips))
    tabs.append(tab)


def _add_paragraph_after(paragraph, text="", style=None):
    p = paragraph._p
    new_p = OxmlElement("w:p")
    p.addnext(new_p)
    new_paragraph = Paragraph(new_p, paragraph._parent)
    if style is not None:
        new_paragraph.style = style
    if text:
        run = new_paragraph.add_run(text)
        run.font.name = "Calibri"
    return new_paragraph


def fill_resume_template(response_tag_answers,
                         template_path="resume_template_sample.docx",
                         output_file="generated_resume.docx"):

    doc = Document(template_path)

    def parse_text_with_tags(paragraph, text, current_tag=None):
        paragraph.clear()

        while text:
            if "<b>" in text and "</b>" in text and text.index("<b>") < text.index("</b>"):
                start = text.index("<b>")
                end = text.index("</b>")

                before = text[:start]
                bold_text = text[start + 3:end]

                if before:
                    run = paragraph.add_run(before)
                    run.font.name = "Calibri"

                if "(" in bold_text and ")" in bold_text:
                    open_idx = bold_text.rfind("(")
                    close_idx = bold_text.rfind(")")
                    if open_idx != -1 and close_idx != -1 and close_idx > open_idx:
                        company_part = bold_text[:open_idx].strip()
                        timeline_part = bold_text[open_idx + 1:close_idx].strip()

                        if company_part and timeline_part:
                            _add_right_tab_stop(paragraph)

                            left_run = paragraph.add_run(company_part + "\t")
                            left_run.font.name = "Calibri"
                            left_run.font.bold = True

                            right_run = paragraph.add_run(timeline_part)
                            right_run.font.name = "Calibri"
                            right_run.font.bold = True
                        else:
                            run = paragraph.add_run(bold_text)
                            run.font.name = "Calibri"
                            run.font.bold = True
                    else:
                        run = paragraph.add_run(bold_text)
                        run.font.name = "Calibri"
                        run.font.bold = True
                else:
                    run = paragraph.add_run(bold_text)
                    run.font.name = "Calibri"
                    run.font.bold = True

                text = text[end + 4:]
            else:
                if text:
                    run = paragraph.add_run(text)
                    run.font.name = "Calibri"
                break

    for paragraph in doc.paragraphs:
        text = paragraph.text

        for tag, value in response_tag_answers.items():
            start_tag = f"<{tag}>"
            end_tag = f"</{tag}>"

            if start_tag in text and end_tag in text:
                new_text = value

                if tag == "6":
                    for prefix in ["Other Skills:", "Soft Skills:", "Domain Experience:"]:
                        new_text = new_text.replace(prefix, "")
                    new_text = " ".join(new_text.split())

                text = text.replace(f"{start_tag}{end_tag}", new_text)
                text = text.replace(f"{start_tag} {end_tag}", new_text)

                parse_text_with_tags(paragraph, text, current_tag=tag)

                if tag == "1":
                    for run in paragraph.runs:
                        run.font.size = Pt(16)
                        run.font.bold = True
                        run.font.color.rgb = RGBColor(0x00, 0x00, 0x00)
                elif tag == "2":
                    for run in paragraph.runs:
                        run.font.size = Pt(16)
                        run.font.bold = True
                        run.font.color.rgb = RGBColor(0x00, 0x00, 0x00)
                elif tag == "3":
                    paragraph.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY

                break

    for paragraph in doc.paragraphs:
        if "<missing_certification>" in paragraph.text:
            p = paragraph._element
            prev = p.getprevious()

            p.getparent().remove(p)
            if prev is not None:
                prev.getparent().remove(prev)
            break

    doc.save(output_file)
    print("Resume generated at Time:", datetime.now())


def process_resume(pdf_path: str, template_path: str, output_path: str):
    resume_text = extract_resume_text(pdf_path)
    print("---------Extraction of resume text is completed-------------")
    system_prompt, user_prompt = get_prompt_for_resume_template_fill(resume_text, template_sample)
    print("---------Extraction of system_prompt, user_prompt is completed-------------")
    response = narrate(system_prompt, user_prompt)
    print("---------Extraction of response is completed-------------")
    parsed = safe_parse(response)
    if not is_valid_json(parsed):
        raise ValueError("Invalid JSON returned from model")
    fill_resume_template(parsed, template_path, output_path)
    print("---------Extraction of response formatting is completed-------------")
    print("---------Saving the generated docx resume file-------------")
    return output_path
