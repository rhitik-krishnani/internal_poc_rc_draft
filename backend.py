import os
import json
import asyncio
import aiohttp
import re
import pdfplumber
from datetime import datetime
from dotenv import load_dotenv

from docx import Document
from docx.shared import RGBColor, Pt
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.text.paragraph import Paragraph

try:
    import streamlit as st
except:
    st = None

load_dotenv()

def get_api_key():
    try:
        key = st.secrets.get("HF_API_KEY") if st else None
    except:
        key = None

    key = key or os.getenv("HF_API_KEY")

    if not key:
        raise ValueError("HF_API_KEY not found")

    return key

HF_API_KEY = get_api_key()

MODEL = "Qwen/Qwen2.5-72B-Instruct"
API_URL = "https://router.huggingface.co/v1/chat/completions"

HEADERS = {
    "Authorization": f"Bearer {HF_API_KEY}",
    "Content-Type": "application/json"
}

# =========================================================
# TEMPLATE
# =========================================================

TEMPLATE_SAMPLE = {
    "1": "Name",
    "2": "Designation or Current Job Title",
    "3": "Professional Summary",
    "4": "Primary Tools",
    "5": "Cloud & Infrastructure",
    "6": "Other Skills",
    "7": "Professional Experience",
    "8": "Certifications"
}

CORE_RULES = """
### UNIVERSAL RULES ###
1. Use ONLY information explicitly present in the resume.
2. Do NOT invent or infer any information.
3. Do NOT create new fields.
4. Preserve factual accuracy.
5. Output must contain ONLY the filled tags.
6. Do NOT include explanations.
"""

JSON_RULES = """
### STRICT JSON FORMATTING RULES ###
- Return ONLY valid JSON.
- Escape all double quotes.
- Replace new lines with \\n
"""

# =========================================================
# 🧠 PROMPTS (SAME STRUCTURE - NO CHANGE)
# =========================================================

def prompt_tag_name(resume_text):
    """Extract: Name"""
    system_prompt = """
You are an expert resume parsing system.
"""
    
    user_prompt = f"""
### RESUME ###
{resume_text}


### TASK: EXTRACT NAME ###
- Ensure to follow {CORE_RULES} and {JSON_RULES} without any failure.
- Extract the candidate's full name.
- Use ONLY the name as explicitly written in the resume.
- Do NOT invent or modify names.

Return ONLY this JSON format:
{{"1": "Full Name Here"}}
"""
    
    return system_prompt, user_prompt

def prompt_tag_designation(resume_text):
    """Extract: Designation / Current Job Title"""
    system_prompt = """
You are an expert resume parsing system.
"""
    
    user_prompt = f"""
### RESUME ###
{resume_text}


### TASK: EXTRACT DESIGNATION ###
- Ensure to follow {CORE_RULES} and {JSON_RULES} without any failure.
- Extract the current or most recent job title/designation.
- If a "Current Title" or "Designation" section exists, use that.
- Otherwise, use the most recent job title from Professional Experience.
- Use ONLY information explicitly present in the resume.
- Do NOT infer or invent designations.

Return ONLY this JSON format:
{{"2": "Job Title Here"}}
"""
    
    return system_prompt, user_prompt

def prompt_tag_professional_summary(resume_text):
    """Extract: Professional Summary (FULL PRESERVATION)"""
    system_prompt = """
You are an expert resume parsing and structured information extraction system.
"""
    
    user_prompt = f"""
### RESUME RAW TEXT ###
{resume_text}


### TASK: EXTRACT PROFESSIONAL SUMMARY ###
- Ensure to follow {CORE_RULES} and {JSON_RULES} without any failure.

### PROFESSIONAL SUMMARY - RULES ###
- Extract the complete Professional Summary exactly as written in the resume.
- Do NOT condense, summarize, shorten, or paraphrase the content.
- Preserve every word exactly as in the original text.
- Remove all special symbols, bullets, or characters (such as ➢, •, -, etc.).
- Present the content in clean paragraph form without changing wording, order, or meaning.
- If no Professional Summary section exists, return nothing.
 
Return ONLY this JSON format:
{{"3": "Full Professional Summary Text Here (preserving all original details)"}}
"""
    
    return system_prompt, user_prompt

def prompt_tag_primary_tools(resume_text):
    """Extract: Primary Tools"""
    system_prompt = """
You are an expert resume parsing system.
"""
    
    user_prompt = f"""
### RESUME ###
{resume_text}

{CORE_RULES}

- Copy the ENTIRE professional summary from the resume word-for-word.
- Do NOT condense, summarize, shorten, or paraphrase the content.
- Preserve every word exactly as in the original text.
- Remove all special symbols, bullets, or characters (such as ➢, •, -, etc.).
- Present the content in clean paragraph form without altering wording, sequence, or meaning.
- If no dedicated Professional Summary section exists, CREATE on in 4-5 lines.

{JSON_RULES}

Return ONLY this JSON format:
{{"4": "Tool1, Tool2, Tool3... OR • Tool1\\n• Tool2\\n• Tool3..."}}
"""
    
    return system_prompt, user_prompt

def prompt_tag_cloud_and_infrastructure(resume_text):
    """Extract: Cloud & Infrastructure"""
    system_prompt = """
You are an expert resume parsing system.
"""
    
    user_prompt = f"""
### RESUME ###
{resume_text}

{CORE_RULES}

### TASK: EXTRACT CLOUD & INFRASTRUCTURE ###
- Extract cloud platforms and infrastructure tools (e.g., AWS, Azure, GCP, Kubernetes, Docker, etc.).
- Cloud & Infrastructure tools may appear in "Skills", "Technical Skills", or "Tools" sections.
- List all cloud platforms and infrastructure tools exactly as written in the resume.
- Do NOT invent technologies not mentioned.
- Include services, platforms, and tools related to cloud and infrastructure only.
- Format: Use bullet points or comma-separated list as originally presented.

{JSON_RULES}

Return ONLY this JSON format:
{{"5": "AWS, Azure, GCP, Docker... OR • AWS\\n• Docker\\n• Kubernetes..."}}
"""
    
    return system_prompt, user_prompt

def prompt_tag_other_skills(resume_text):
    """Extract: Other Skills (Non-technical)"""
    system_prompt = """
You are an expert resume parsing system.
"""
    
    user_prompt = f"""
### RESUME ###
{resume_text}

{CORE_RULES}

### TASK: EXTRACT OTHER SKILLS ###
- Extract skills that are NOT primary tools, programming languages, or cloud/infrastructure platforms.
- Examples: Communication, Leadership, Project Management, Data Analysis, Problem Solving, etc.
- Look for "Skills", "Additional Skills", "Soft Skills", or similar sections.
- Include all skills not categorized under Primary Tools or Cloud & Infrastructure.
- Do NOT invent skills not mentioned in the resume.
- Format: Use bullet points or comma-separated list as originally presented.
- List all skills exactly as written.

{JSON_RULES}

Return ONLY this JSON format:
{{"6": "Skill1, Skill2, Skill3... OR • Skill1\\n• Skill2\\n• Skill3..."}}
"""
    
    return system_prompt, user_prompt

def prompt_tag_professional_experience(resume_text):
    """Extract: Professional Experience (FULL PRESERVATION + STRICT FORMATTING)"""
    system_prompt = """
You are an expert resume parsing and structured information extraction system.
"""
    
    user_prompt = f"""
### RESUME RAW TEXT ###
{resume_text}

{CORE_RULES}

### TASK: EXTRACT PROFESSIONAL EXPERIENCE ###

### PROFESSIONAL EXPERIENCE — STRICT FORMATTING RULES ###

**PRESERVE ALL PROJECT DETAILS - DO NOT TRIM:**
- Copy ALL project information exactly as written in the resume.
- Include EVERY responsibility, achievement, and detail.
- Do NOT abbreviate or summarize project descriptions.
- Do NOT remove any bullet points or details.
- Do NOT summarize, condense, abbreviate, or trim ANY information.
- Do NOT paraphrase or rewrite. Use original text verbatim.

RULE 1 — COMPANY NAME:
- Print the company name ONLY ONCE — at the very top, before any roles.
- Do NOT repeat the company name for subsequent roles under the same company.

RULE 2 — STRUCTURE ORDER (always follow this exact order):
  1. Company name + timeline
  2. Role title
  3. Projects under that role (if any) - PRESERVE ALL DETAILS
  4. (blank line)
  5. Next role title (if same company)
  6. Projects under that role (if any) - PRESERVE ALL DETAILS
  7. (blank line)
  8. Next company name + timeline (if different company) and so on.

NOTE: 
- Timeline will ONLY be mentioned for the Company Name in the output.
- ENSURE wherever you provide timeline, the format should be Timeline mmm-yy like Jan 26 - Oct 25 or Jan-25 - present, whichever is applicable. Do not provide tenure anywhere.

RULE 3 — WRAPPING (CRITICAL TO FOLLOW):
- Wrap Company Name and Timeline inside <b> tags.
- Wrap every Role title inside <b> tags. Do NOT include timeline, duration, or pipe symbol (|) in role tags.
- Wrap every Project name inside <b> tags. Do NOT include timeline, duration, or pipe symbol (|) in project tags.

RULE 4 — MANDATORY EXAMPLES (follow this exact pattern):

Single role at a company:
<b> Company ABC (Jan 2018 - Dec 2019) </b>
<b> Software Engineer </b>
<b> Project: Project Alpha </b>
• Responsibility 1
• Responsibility 2
• Responsibility 3

Multiple roles at the same company (company name appears ONLY ONCE):
<b> Company XYZ (Mar 2020 - Present) </b>

<b> Senior Engineer </b>
<b> Project: Project Gamma </b>
• Responsibility 1
• Responsibility 2

<b> Project: Project Delta </b>
• Responsibility 1
• Responsibility 2

<b> Junior Engineer </b>
<b> Project: Project Epsilon </b>
• Responsibility 1
• Responsibility 2

Multiple companies (repeat full structure per company):
<b> Company XYZ (Mar 2020 - Present) </b>

<b> Senior Engineer </b>
<b> Project: Project Gamma </b>
• Responsibility 1
• Responsibility 2

<b> Company ABC (Jan 2018 - Feb 2020) </b>

<b> Analyst </b>
<b> Project: Project Zeta </b>
• Responsibility 1
• Responsibility 2

ENSURE NOT to deviate from this structure under any circumstances.

{JSON_RULES}

Return ONLY this JSON format:
{{"7": "Complete Professional Experience formatted as shown above, with all details preserved"}}
"""
    
    return system_prompt, user_prompt


def prompt_tag_certifications(resume_text):
    """Extract: Certifications (SPECIAL HANDLING)"""
    system_prompt = """
You are an expert resume parsing system.
"""
    
    user_prompt = f"""
### RESUME ###
{resume_text}

{CORE_RULES}

### TASK: EXTRACT CERTIFICATIONS ###

### CERTIFICATIONS — STRICT RULES ###
- Extract all certifications, licenses, or credentials from the resume.
- Look for "Certifications", "Licenses", "Credentials", "Certifications & Awards" sections.
- Each unique certification must be on a new line.
- Do NOT invent or infer certifications.
- Use ONLY certifications explicitly mentioned in the resume.
- If NO certifications are found in the resume, return EXACTLY: <missing_certification></missing_certification>
- Preserve certification names exactly as written.

Format when certifications exist:
• Certification 1
• Certification 2
• Certification 3

{JSON_RULES}

Return ONLY this JSON format:
{{"8": "• Certification 1\\n• Certification 2\\n• Certification 3"}} 
OR if no certifications:
{{"8": "<missing_certification></missing_certification>"}}
"""
    
    return system_prompt, user_prompt

PROMPT_FUNCTION_MAP = {
    "1": prompt_tag_name,
    "2": prompt_tag_designation,
    "3": prompt_tag_professional_summary,
    "4": prompt_tag_primary_tools,
    "5": prompt_tag_cloud_and_infrastructure,
    "6": prompt_tag_other_skills,
    "7": prompt_tag_professional_experience,
    "8": prompt_tag_certifications,
}

# ---------------- PDF ----------------

def extract_resume_text(pdf_path):
    text = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            t = page.extract_text()
            if t:
                text.append(t)
    return "\n".join(text)

# ---------------- PARSER ----------------

def safe_parse(response):
    cleaned = response.strip()
    cleaned = re.sub(r'^```json\s*', '', cleaned)
    cleaned = re.sub(r'^```\s*', '', cleaned)
    cleaned = re.sub(r'\s*```$', '', cleaned)

    start = cleaned.find("{")
    end = cleaned.rfind("}")

    if start == -1 or end == -1:
        raise ValueError("Invalid JSON")

    cleaned = cleaned[start:end+1]
    cleaned = re.sub(r'(?<!\\)\n', '\\n', cleaned)

    return json.loads(cleaned)

# ---------------- API ----------------

async def narrate_async(session, system_prompt, user_prompt, tag):
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        "temperature": 0.0,
        "max_tokens": 1024
    }

    async with session.post(API_URL, headers=HEADERS, json=payload) as resp:
        data = await resp.json()
        return data["choices"][0]["message"]["content"]

# ---------------- PROCESS ----------------

async def process_tag(session, tag, resume_text):
    try:
        func = PROMPT_FUNCTION_MAP[tag]
        sp, up = func(resume_text)
        response = await narrate_async(session, sp, up, tag)
        parsed = safe_parse(response)

        if tag not in parsed:
            raise ValueError(f"Tag {tag} missing")

        return parsed

    except:
        return {tag: ""}

async def process_all(resume_text):
    async with aiohttp.ClientSession() as session:
        tasks = [
            process_tag(session, tag, resume_text)
            for tag in TEMPLATE_SAMPLE.keys()
        ]
        results = await asyncio.gather(*tasks)

    return results

def merge_results(results):
    final = {}
    for r in results:
        final.update(r)
    return dict(sorted(final.items(), key=lambda x: int(x[0])))

# ---------------- DOCX ----------------

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

def fill_resume_template(response_tag_answers, template_path, output_file):
    doc = Document(template_path)

    for paragraph in doc.paragraphs:
        text = paragraph.text

        for tag, value in response_tag_answers.items():
            start_tag = f"<{tag}>"
            end_tag = f"</{tag}>"

            if start_tag in text and end_tag in text:
                paragraph.text = text.replace(f"{start_tag}{end_tag}", value)

    doc.save(output_file)

# ---------------- MAIN ----------------

async def run_pipeline(pdf_path, template_path, output_path):
    text = extract_resume_text(pdf_path)
    results = await process_all(text)
    merged = merge_results(results)

    fill_resume_template(
        response_tag_answers=merged,
        template_path=template_path,
        output_file=output_path
    )

# ---------------- WRAPPER (IMPORTANT FIX) ----------------

def process_resume(pdf_path, template_path, output_path):
    asyncio.run(run_pipeline(pdf_path, template_path, output_path))
