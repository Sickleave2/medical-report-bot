# pdf_processor.py
import fitz
import io
import random
import re
from datetime import datetime

class SmartPDFProcessor:
    
    @staticmethod
    def analyze_pdf(pdf_path):
        """تحليل الملف واستخراج أسماء الحقول وحالتها"""
        doc = fitz.open(pdf_path)
        fields = []
        for page in doc:
            for widget in page.widgets():
                name = widget.field_name
                value = widget.field_value
                status = "ممتلئ" if value and str(value).strip() else "فارغ"
                display_value = value if status == "ممتلئ" else ""
                
                fields.append({
                    "name": name,
                    "status": status,
                    "value": display_value
                })
        doc.close()
        return fields

    @staticmethod
    def generate_medical_file_no():
        """توليد رقم الملف الطبي: 26 + الشهر + اليوم + 3 أرقام عشوائية"""
        now = datetime.now()
        prefix = f"26{now.strftime('%m%d')}"  # 260226 مثلاً
        suffix = "".join([str(random.randint(0, 9)) for _ in range(3)])
        return prefix + suffix

    @staticmethod
    def fill_dynamic_pdf(template_path, user_data, selected_fields):
        """تعبئة الحقول التي اختارها المطور فقط من بيانات المستخدم"""
        doc = fitz.open(template_path)
        file_no = SmartPDFProcessor.generate_medical_file_no()
        
        for page in doc:
            for widget in page.widgets():
                field_name = widget.field_name
                
                # إذا كان الحقل ضمن الحقول المسموحة (✅)
                if field_name in selected_fields:
                    field_name_lower = field_name.lower()
                    
                    # الربط الذكي: البوت يطابق اسم الحقل البرمجي بنوع البيانات
                    if "name" in field_name_lower or "اسم" in field_name_lower:
                        widget.field_value = user_data.get("patient_name", "")
                        
                    elif "age" in field_name_lower or "عمر" in field_name_lower:
                        widget.field_value = str(user_data.get("age", ""))
                        
                    elif "work" in field_name_lower or "employer" in field_name_lower or "عمل" in field_name_lower:
                        widget.field_value = user_data.get("employer", "")
                        
                    elif "file" in field_name_lower or "رقم" in field_name_lower or "no" in field_name_lower:
                        widget.field_value = file_no
                        
                    elif "date" in field_name_lower or "تاريخ" in field_name_lower:
                        widget.field_value = user_data.get("date", "")
                        
                    elif "days" in field_name_lower or "ايام" in field_name_lower or "أيام" in field_name_lower:
                        widget.field_value = str(user_data.get("days", ""))
                    
                    widget.update()
                    
        # حفظ الملف في الذاكرة لتصديره مباشرة
        output = io.BytesIO()
        doc.save(output)
        doc.close()
        output.seek(0)
        return output
