# pdf_filler.py
import fitz
import logging
from typing import Dict

logger = logging.getLogger(__name__)

def fill_pdf_form(template_path: str, output_stream, data: Dict):
    """
    تعبئة حقول PDF بناءً على قاموس البيانات.
    data مفتاح = اسم الحقل، قيمة = القيمة.
    """
    doc = fitz.open(template_path)
    filled = False
    for page in doc:
        widgets = page.widgets()
        if widgets:
            for w in widgets:
                field_name = w.field_name
                if field_name and field_name in data:
                    w.field_value = str(data[field_name])
                    w.update()
                    filled = True
                elif field_name:
                    logger.debug(f"Field '{field_name}' not found in data")
    if not filled:
        logger.warning("No fields were filled in the PDF")
    doc.save(output_stream)
    doc.close()

def create_field_map(user_data: Dict) -> Dict:
    """
    إنشاء خريطة بين أسماء الحقول في PDF والبيانات المدخلة.
    يمكن توسيعها حسب الحقول الفعلية في القالب.
    """
    return {
        "full_name_ar": user_data.get("patient_name_ar", ""),
        "full_name_en": user_data.get("patient_name_en", ""),
        "file_no": user_data.get("file_no", ""),
        "age": str(user_data.get("age", "")),
        "employer_ar": user_data.get("employer", ""),
        "employer_en": user_data.get("employer_en", ""),
        "nationality_ar": user_data.get("nationality_ar", "سعودي"),
        "nationality_en": user_data.get("nationality_en", "Saudi"),
        "clinic_date_ar": user_data.get("clinic_date_ar", ""),
        "clinic_date_en": user_data.get("clinic_date_en", ""),
        "admission_date_ar": user_data.get("admission_date_ar", ""),
        "admission_date_en": user_data.get("admission_date_en", ""),
        "discharge_date_ar": user_data.get("discharge_date_ar", ""),
        "discharge_date_en": user_data.get("discharge_date_en", ""),
        "leave_days": str(user_data.get("leave_days", "")),
        "start_date_ar": user_data.get("start_date_ar", ""),
        "start_date_en": user_data.get("start_date_en", ""),
        "end_date_ar": user_data.get("end_date_ar", ""),
        "end_date_en": user_data.get("end_date_en", ""),
        "male_checkbox": "Yes" if user_data.get("gender") == "ذكر" else "Off",
        "female_checkbox": "Yes" if user_data.get("gender") == "أنثى" else "Off",
  }
