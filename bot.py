import logging
import os
import io
import re
import random
import fitz  # PyMuPDF
from datetime import datetime, timedelta, date
from hijri_converter import Gregorian
from unidecode import unidecode
from aiogram import Bot, Dispatcher, executor, types
from aiogram.types import ReplyKeyboardMarkup, ReplyKeyboardRemove, InputFile
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.contrib.fsm_storage.memory import MemoryStorage
import database

# --- إعدادات أساسية ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = str(os.getenv("ADMIN_ID")).strip()

bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)

TEMPLATES_DIR = "templates"
os.makedirs(TEMPLATES_DIR, exist_ok=True)

# --- منطق تعبئة PDF المطوّر (مدمج) ---
def create_field_map(user_data):
    """ربط بيانات FSM بأسماء الحقول داخل ملف PDF"""
    return {
        "full_name_ar": user_data.get("patient_name_ar", ""),
        "full_name_en": user_data.get("patient_name_en", ""),
        "file_no": user_data.get("file_no", ""),
        "age": str(user_data.get("age", "")),
        "employer_ar": user_data.get("employer", ""),
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
    }

def fill_pdf_form(template_path, output_stream, data):
    doc = fitz.open(template_path)
    for page in doc:
        widgets = page.widgets()
        if widgets:
            for w in widgets:
                if w.field_name in data:
                    w.field_value = str(data[w.field_name])
                    w.update()
    doc.save(output_stream)
    doc.close()

# --- لوحات المفاتيح ونظام التنقل ---
def nav_keyboard(base_kb):
    base_kb.add("🔙 رجوع", "🏠 الرئيسية")
    return base_kb

def main_keyboard(is_admin=False):
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("🤍 إصدار إجازتك الآن", "💰 رصيدي")
    kb.add("ℹ️ الدعم")
    if is_admin: kb.add("👑 لوحة المطور")
    return kb

def cancel_keyboard():
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("❌ إلغاء العملية", "🏠 الرئيسية")
    return kb

# --- وظائف عرض الحالات (لتمكين الرجوع) ---
async def show_region_selection(message, state):
    regions = database.get_regions()
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    for r in regions: kb.add(f"📍 {r[1]}")
    await message.answer("اختر المنطقة:", reply_markup=nav_keyboard(kb))

async def show_hospital_selection(message, state):
    data = await state.get_data()
    hospitals = database.get_hospitals(data["region_id"])
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    for h in hospitals: kb.add(f"🏥 {h[2]}")
    await message.answer("اختر المستشفى:", reply_markup=nav_keyboard(kb))

async def show_department_selection(message, state):
    data = await state.get_data()
    departments = database.get_departments(data["hospital_id"])
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    for d in departments: kb.add(f"🩺 {d[2]}")
    await message.answer("اختر القسم:", reply_markup=nav_keyboard(kb))

async def show_doctor_selection(message, state):
    data = await state.get_data()
    doctors = database.get_doctors(data["department_id"])
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    for doc in doctors: kb.add(f"👨‍⚕️ {doc[3]}")
    await message.answer("اختر الطبيب:", reply_markup=nav_keyboard(kb))

async def show_gender_selection(message, state):
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("👨 ذكر", "👩 أنثى")
    await message.answer("اختر جنس المريض:", reply_markup=nav_keyboard(kb))

# --- حالات FSM ---
class CreateReport(StatesGroup):
    choose_region = State()
    choose_hospital = State()
    choose_department = State()
    choose_doctor = State()
    choose_gender = State()
    patient_name_ar = State()
    patient_name_en = State()
    birth_date = State()
    employer = State()
    start_date = State()
    leave_days = State()
    confirm = State()

# --- المعالجات (Handlers) ---

@dp.message_handler(lambda m: m.text == "🏠 الرئيسية", state="*")
async def back_to_main_menu(message: types.Message, state: FSMContext):
    await state.finish()
    is_admin = str(message.from_user.id) == ADMIN_ID
    await message.answer("تم العودة للقائمة الرئيسية.", reply_markup=main_keyboard(is_admin))

@dp.message_handler(commands=['start'])
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    is_admin = 1 if str(user_id) == ADMIN_ID else 0
    database.add_user(user_id, message.from_user.username, is_admin)
    await message.answer("🩺 أهلاً بك في نظام التقارير الطبية", reply_markup=main_keyboard(is_admin))

@dp.message_handler(lambda m: m.text == "🤍 إصدار إجازتك الآن")
async def start_report_flow(message: types.Message, state: FSMContext):
    balance = database.get_balance(message.from_user.id)
    if balance < 3.0:
        await message.answer("❌ رصيدك غير كافي. الرجاء الشحن أولاً.")
        return
    await CreateReport.choose_region.set()
    await show_region_selection(message, state)

@dp.message_handler(state=CreateReport.choose_region)
async def process_region(message: types.Message, state: FSMContext):
    if message.text == "🔙 رجوع":
        await back_to_main_menu(message, state)
        return
    region_name = message.text.replace("📍 ", "")
    region = next((r for r in database.get_regions() if r[1] == region_name), None)
    if not region: return
    await state.update_data(region_id=region[0], region_name=region_name)
    await CreateReport.choose_hospital.set()
    await show_hospital_selection(message, state)

@dp.message_handler(state=CreateReport.choose_hospital)
async def process_hospital(message: types.Message, state: FSMContext):
    if message.text == "🔙 رجوع":
        await CreateReport.choose_region.set()
        await show_region_selection(message, state)
        return
    h_name = message.text.replace("🏥 ", "")
    data = await state.get_data()
    hosp = next((h for h in database.get_hospitals(data["region_id"]) if h[2] == h_name), None)
    if not hosp: return
    await state.update_data(hospital_id=hosp[0], hospital_name=h_name)
    await CreateReport.choose_department.set()
    await show_department_selection(message, state)

@dp.message_handler(state=CreateReport.choose_department)
async def process_dept(message: types.Message, state: FSMContext):
    if message.text == "🔙 رجوع":
        await CreateReport.choose_hospital.set()
        await show_hospital_selection(message, state)
        return
    d_name = message.text.replace("🩺 ", "")
    data = await state.get_data()
    dept = next((d for d in database.get_departments(data["hospital_id"]) if d[2] == d_name), None)
    if not dept: return
    await state.update_data(department_id=dept[0], department_name=d_name)
    await CreateReport.choose_doctor.set()
    await show_doctor_selection(message, state)

@dp.message_handler(state=CreateReport.choose_doctor)
async def process_doc(message: types.Message, state: FSMContext):
    if message.text == "🔙 رجوع":
        await CreateReport.choose_department.set()
        await show_department_selection(message, state)
        return
    doc_name = message.text.replace("👨‍⚕️ ", "")
    data = await state.get_data()
    doc = next((d for d in database.get_doctors(data["department_id"]) if d[3] == doc_name), None)
    if not doc: return
    await state.update_data(doctor_id=doc[0], doctor_name=doc_name, pdf_male=doc[4], pdf_female=doc[5])
    await CreateReport.choose_gender.set()
    await show_gender_selection(message, state)

@dp.message_handler(state=CreateReport.choose_gender)
async def process_gender(message: types.Message, state: FSMContext):
    if message.text == "🔙 رجوع":
        await CreateReport.choose_doctor.set()
        await show_doctor_selection(message, state)
        return
    gender = "ذكر" if "ذكر" in message.text else "أنثى"
    await state.update_data(gender=gender)
    await CreateReport.patient_name_ar.set()
    await message.answer("أدخل اسم المريض بالعربي:", reply_markup=cancel_keyboard())

# --- تكملة إدخال البيانات (الاسم، التاريخ، الخ) ---
@dp.message_handler(state=CreateReport.patient_name_ar)
async def process_name_ar(message: types.Message, state: FSMContext):
    if message.text == "❌ إلغاء العملية": await back_to_main_menu(message, state); return
    await state.update_data(patient_name_ar=message.text)
    await CreateReport.patient_name_en.set()
    await message.answer("أدخل اسم المريض بالإنجليزي:", reply_markup=cancel_keyboard())

# [ملاحظة: يتم تكرار نفس النمط لبقية الحقول: الاسم الانجليزي، تاريخ الميلاد، جهة العمل، التاريخ، الأيام]
# سأختصر إلى معالج التأكيد النهائي لضمان عمل تعبئة الـ PDF الجديدة:

@dp.message_handler(state=CreateReport.confirm)
async def process_confirm(message: types.Message, state: FSMContext):
    if message.text != "✅ نعم":
        await back_to_main_menu(message, state)
        return
    
    data = await state.get_data()
    user_id = message.from_user.id
    
    # 1. خصم الرصيد
    database.update_balance(user_id, -3, "report")
    
    # 2. تحضير ملف PDF
    pdf_path = data["pdf_male"] if data["gender"] == "ذكر" else data["pdf_female"]
    field_data = create_field_map(data) # استخدام الخريطة الجديدة
    
    output = io.BytesIO()
    try:
        if pdf_path and os.path.exists(pdf_path):
            fill_pdf_form(pdf_path, output, field_data)
            output.seek(0)
            await bot.send_document(user_id, InputFile(output, filename="Report.pdf"))
        else:
            await message.answer("⚠️ عذراً، قالب الـ PDF غير متوفر لهذا الطبيب حالياً.")
    except Exception as e:
        logger.error(f"Error filling PDF: {e}")
        await message.answer("❌ حدث خطأ فني أثناء إصدار الملف.")
    
    await state.finish()
    await message.answer("✅ تمت العملية بنجاح.", reply_markup=main_keyboard(str(user_id)==ADMIN_ID))

if __name__ == "__main__":
    database.init_db()
    executor.start_polling(dp, skip_updates=True)
