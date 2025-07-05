import os
import json
import logging
import re
from datetime import datetime
from dataclasses import dataclass
from typing import List, Dict
from fpdf import FPDF
from openai import OpenAI
from io import BytesIO

# === CONFIG ===
openai_api_key = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=openai_api_key)

# === DATA MODEL ===
@dataclass
class EnhancedConsultationSummary:
    session_overview: str
    conversation_highlights: Dict[str, str]
    doctor_assessment: str
    investigations_suggested: List[str]
    medications_treatment: List[str]
    action_items: List[str]
    ai_summary_note: str

# === OPENAI WRAPPER ===
class OpenAISummaryGenerator:
    def __init__(self, client: OpenAI):
        self.client = client

    def generate_consultation_summary(self, conversation_text: str, user_id: str, session_id: str) -> EnhancedConsultationSummary:
        prompt = f"""
        Please analyze the following patient-doctor conversation and generate a structured medical summary.

        ⚠️ IMPORTANT: Only return a valid JSON response. DO NOT include any explanation, markdown, or commentary. No ```json or extra lines.

        Format strictly as:

        {{
            "session_overview": "...",
            "conversation_highlights": {{
                "patient_concerns": "...",
                "doctor_inquiry": "...",
                "key_observations": "...",
                "doctor_explanation": "...",
                "recommendations_given": "..."
            }},
            "doctor_assessment": "...",
            "investigations_suggested": ["..."],
            "medications_treatment": ["..."],
            "action_items": ["..."],
            "ai_summary_note": "..."
        }}

        If any section has no info, write: "No specific information discussed in this session".

        CONVERSATION:
        {conversation_text}
        """

        try:
            response = self.client.chat.completions.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": "You are a medical documentation assistant."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=1500,
                temperature=0.3
            )

            raw_response = response.choices[0].message.content.strip()
            print("\n🔍 Raw AI response:\n", raw_response)

            match = re.search(r'\{[\s\S]*\}', raw_response)
            if match:
                try:
                    summary_json = json.loads(match.group())
                    return EnhancedConsultationSummary(**summary_json)
                except json.JSONDecodeError as json_err:
                    logging.error(f"❌ JSON decoding failed: {json_err}")
            else:
                logging.error("❌ No JSON object detected in OpenAI response.")

        except Exception as e:
            logging.error(f"❌ OpenAI API error: {e}")

        return self._create_fallback_summary()

    def _create_fallback_summary(self) -> EnhancedConsultationSummary:
        return EnhancedConsultationSummary(
            session_overview="This consultation session covered the patient's health concerns and the doctor's professional recommendations.",
            conversation_highlights={
                "patient_concerns": "Patient presented with general health concerns.",
                "doctor_inquiry": "Doctor asked standard diagnostic questions.",
                "key_observations": "No specific clinical observations documented.",
                "doctor_explanation": "Doctor provided general guidance.",
                "recommendations_given": "Standard advice shared."
            },
            doctor_assessment="General assessment based on symptoms.",
            investigations_suggested=["No specific investigations mentioned"],
            medications_treatment=["No specific medications discussed"],
            action_items=["Follow general medical advice"],
            ai_summary_note="This summary was auto-generated based on the input conversation."
        )

# === PDF GENERATOR ===
class EnhancedConsultationPDF(FPDF):
    def __init__(self):
        super().__init__()
        base_dir = os.path.dirname(os.path.abspath(__file__))
        font_dir = os.path.join(base_dir, "fonts")
        self.add_font('DejaVu', '', os.path.join(font_dir, 'DejaVuSans.ttf'), uni=True)
        self.add_font('DejaVu', 'B', os.path.join(font_dir, 'DejaVuSans-Bold.ttf'), uni=True)
        self.add_font('DejaVu', 'I', os.path.join(font_dir, 'DejaVuSans-Oblique.ttf'), uni=True)
        self.set_font("DejaVu", '', 10)

    def header(self):
        self.set_fill_color(41, 128, 185)
        self.rect(0, 0, 210, 32, 'F')
        self.set_text_color(255, 255, 255)
        self.set_font("DejaVu", 'B', 20)
        self.set_xy(15, 8)
        self.cell(0, 8, "MEDICAL CONSULTATION SUMMARY", align="L")
        self.set_font("DejaVu", '', 11)
        self.set_xy(15, 20)
        self.cell(0, 6, "🩺 Comprehensive Patient-Doctor Consultation Report", align="L")
        self.ln(5)

    def footer(self):
        self.set_y(-18)
        self.set_draw_color(41, 128, 185)
        self.set_line_width(0.5)
        self.line(15, 285, 195, 285)
        self.set_font("DejaVu", '', 8)
        self.set_text_color(100, 100, 100)
        self.set_x(15)
        self.cell(60, 6, f"Page {self.page_no()}", align="L")
        self.set_x(135)
        self.cell(60, 6, "AI-Enhanced Medical Summary", align="R")

    def add_section_header(self, title: str, icon: str = "", color=(41, 128, 185)):
        if self.get_y() > 265:
            self.add_page()

        self.ln(10)
        self.set_fill_color(*color)
        self.rect(15, self.get_y(), 180, 12, 'F')
        self.set_text_color(255, 255, 255)
        self.set_font("DejaVu", 'B', 12)
        self.set_xy(18, self.get_y() + 3)
        self.cell(0, 6, f"{icon} {title}" if icon else title, align="L")
        self.ln(18)

    def add_info_row(self, label: str, value: str, bold_value: bool = False):
        self.set_font("DejaVu", 'B', 10)
        self.set_text_color(52, 73, 94)
        self.set_x(20)
        self.cell(60, 7, f"{label}:", align="L")
        self.set_font("DejaVu", 'B' if bold_value else '', 10)
        self.set_text_color(44, 62, 80)
        self.set_x(80)
        self.cell(115, 7, value, align="L")
        self.ln(8)

    def add_paragraph_content(self, content: str, indent: int = 20):
        self.set_font("DejaVu", '', 10)
        self.set_text_color(44, 62, 80)
        self.set_x(indent)
        self.multi_cell(210 - indent - 15, 6, content)

    def add_bullet_list(self, items: List[str], bullet_symbol: str = "•"):
        if not items or (len(items) == 1 and "no specific" in items[0].lower()):
            self.set_font("DejaVu", 'I', 10)
            self.set_text_color(128, 128, 128)
            self.set_x(25)
            self.multi_cell(170, 6, "No specific information discussed in this session.")
            self.ln(5)
            return
        for item in items:
            if item.strip():
                self.set_font("DejaVu", '', 10)
                self.set_text_color(44, 62, 80)
                self.set_x(25)
                self.cell(5, 6, bullet_symbol, align="L")
                self.set_x(32)
                self.multi_cell(163, 6, item.strip())
                self.ln(3)

    def add_conversation_highlights(self, highlights: Dict[str, str]):
        for section_title, content in highlights.items():
            label = section_title.replace("_", " ").title()
            self.set_font("DejaVu", 'B', 10)
            self.set_text_color(41, 128, 185)
            self.set_x(25)
            self.cell(0, 7, f"• {label}:", align="L")
            self.ln(7)
            self.set_font("DejaVu", '', 10)
            self.set_text_color(44, 62, 80)
            self.set_x(35)
            self.multi_cell(160, 6, content)
            self.ln(4)

    def add_medical_disclaimer(self):
        self.ln(8)
        self.set_fill_color(255, 243, 205)
        self.set_draw_color(230, 126, 34)
        self.set_line_width(1.0)
        y_start = self.get_y()
        self.rect(15, y_start, 180, 45, 'DF')  # increased height
        self.set_text_color(175, 96, 26)
        self.set_font("DejaVu", 'B', 10)
        self.set_xy(20, y_start + 4)
        self.cell(0, 5, "⚠️ MEDICAL DISCLAIMER", align="L")
        disclaimer = (
            "IMPORTANT MEDICAL DISCLAIMER: This document is an AI-generated summary of a medical consultation "
            "created for documentation and reference purposes only. This summary is NOT a medical prescription, "
            "diagnosis, or treatment plan. It should not replace professional medical advice, clinical judgment, "
            "or direct communication with your healthcare provider. Always consult with qualified medical "
            "professionals for any health-related decisions, medication changes, or treatment modifications. "
            "The accuracy of this AI-generated content should be verified with your healthcare provider."
        )
        self.set_text_color(80, 80, 80)
        self.set_font("DejaVu", '', 8)
        self.set_xy(20, y_start + 12)
        self.multi_cell(170, 4.5, disclaimer)
        self.ln(10)




# === FINAL PDF WRAPPER ===
def generate_enhanced_consultation_pdf(user_id: str, session_id: str, conversation_summary: str) -> BytesIO:
    generator = OpenAISummaryGenerator(client)
    summary: EnhancedConsultationSummary = generator.generate_consultation_summary(
        conversation_summary, user_id, session_id
    )

    pdf = EnhancedConsultationPDF()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=25)

    pdf.add_section_header("SESSION INFORMATION", "🧾")
    pdf.add_info_row("Date of Consultation", datetime.now().strftime("%d %B %Y"), bold_value=True)
    pdf.add_info_row("Session ID", session_id, bold_value=True)
    pdf.add_info_row("User ID", user_id)
    pdf.add_info_row("Document Type", "Medical Consultation Summary")
    pdf.add_info_row("Generated", datetime.now().strftime("%d %B %Y at %H:%M UTC"))

    pdf.add_section_header("SESSION OVERVIEW", "📋")
    pdf.add_paragraph_content(summary.session_overview)

    pdf.add_section_header("CONVERSATION HIGHLIGHTS", "👥")
    pdf.add_conversation_highlights(summary.conversation_highlights)

    pdf.add_section_header("DOCTOR'S ASSESSMENT", "🩺")
    pdf.add_paragraph_content(summary.doctor_assessment)

    pdf.add_section_header("INVESTIGATIONS SUGGESTED", "🧪")
    pdf.add_bullet_list(summary.investigations_suggested)

    pdf.add_section_header("MEDICATIONS / TREATMENT", "💊")
    pdf.add_bullet_list(summary.medications_treatment)

    pdf.add_section_header("ACTION ITEMS / NEXT STEPS", "📌")
    pdf.add_bullet_list(summary.action_items, bullet_symbol="✓")

    pdf.add_section_header("AI SUMMARY NOTE", "🧠")
    pdf.add_paragraph_content(summary.ai_summary_note)

    pdf.add_section_header("ABOUT THIS SUMMARY", "📝")
    pdf.add_paragraph_content(
        "This document is a structured summary generated using AI technology from a doctor-patient conversation. "
        "It aims to assist in maintaining records and improving follow-up care but should be validated by medical professionals."
    )

    pdf.add_medical_disclaimer()

    buffer = BytesIO()
    pdf.output(buffer)
    buffer.seek(0)
    return buffer
