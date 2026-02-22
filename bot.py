import logging
import os
import io
import re
import random
import fitz  # PyMuPDF
from datetime import datetime, timedelta, date
from dateutil.relativedelta import relativedelta
from hijri_converter import Gregorian
from unidecode import unidecode
from aiogram import Bot, Dispatcher, executor, types
from aiogram.types import ReplyKeyboardMarkup, InputFile
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.contrib.fsm_storage.memory import MemoryStorage
import database

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = str(os.getenv("ADMIN_ID")).strip()

logging.basicConfig(level=logging.INFO)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot, storage=MemoryStorage())

TEMPLATES_DIR = "templates"
os.makedirs(TEMPLATES_DIR, exist_ok=True)

database.init_db()
database.seed_regions()

# ========== دوال مساعدة ==========
def slugify(text):
    """تحويل النص إلى كود مختصر (أحرف صغيرة بدون مسافات)"""
    text = unidecode(text).lower()
    text = re.sub(r'\s+', '_', text)
    text = re.sub(r'[^a-z0-9_]', '', text)
    return text[:10]

def get_template_path(region_name, hospital_name, department_name, gender):
    """إنشاء مسار لحفظ القالب"""
    region_code = slugify(region_name)[:3]
    hospital_code = slugify(hospital_name)[:3]
    dept_code = slugify(department_name)[:3]
    filename = f"{region_code}_{hospital_code}_{dept_code}_{gender}.pdf"
    folder = os.path.join(TEMPLATES_DIR, f"{region_code}_{hospital_code}_{dept_code}")
    os.makedirs(folder, exist_ok=True)
    return os.path.join(folder, filename)

def extract_form_fields(pdf_path):
    """استخراج أسماء الحقول من PDF Form"""
    doc = fitz.open(pdf_path)
    fields = []
    for page in doc:
        widgets = page.widgets()
        if widgets:
            for w in widgets:
                if w.field_name:
                    fields.append(w.field_name)
    doc.close()
    return fields

def fill_pdf_form(template_path, output_stream, data):
    """
    تعبئة حقول PDF بناءً على قاموس البيانات.
    data مفتاح = field_name, قيمة = value.
    """
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

def generate_file_no(start_date):
    # start_date: date object
    yymmdd = start_date.strftime("%y%m%d")  # 260815
    random_part = f"{random.randint(100, 999)}"
    return yymmdd + random_part

def calculate_age(birth_date):
    today = date.today()
    age = today.year - birth_date.year - ((today.month, today.day) < (birth_date.month, birth_date.day))
    return age

def gregorian_to_hijri(date_obj):
    h = Gregorian.fromdate(date_obj).to_hijri()
    return f"{h.year}-{h.month:02d}-{h.day:02d}"

def translate_arabic_to_english(text):
    """ترجمة بسيطة للاسم أو النص (يمكن تحسينها بقاموس)"""
    return unidecode(text)

def validate_date(date_text):
    try:
        datetime.strptime(date_text, "%Y-%m-%d")
        return True
    except ValueError:
        return False

def doctor_has_templates(doctor_id):
    doctor = database.get_doctor(doctor_id)
    return doctor and doctor[4] and doctor[5]  # template_male and template_female

# ========== لوحات المفاتيح ==========
def main_keyboard(is_admin=False):
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("🤍 إصدار إجازتك الآن", "💰 رصيدي")
    kb.add("ℹ️ الدعم")
    if is_admin:
        kb.add("👑 لوحة المطور")
    return kb

def admin_keyboard():
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("💰 إدارة الرصيد", "📍 إدارة المناطق")
    kb.add("🏥 إدارة المستشفيات", "🩺 إدارة الأقسام")
    kb.add("👨‍⚕️ إدارة الأطباء", "📊 الإحصائيات")
    kb.add("📢 الإشعارات", "🛠 إعداد وتعديل نظام التقارير")
    kb.add("🔙 رجوع")
    return kb

def balance_management_keyboard():
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("➕ إضافة رصيد", "➖ خصم رصيد")
    kb.add("👤 معلومات مستخدم", "🚫 حظر", "🔓 فك حظر")
    kb.add("🔙 رجوع")
    return kb

def yes_no_keyboard():
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("✅ نعم", "❌ لا")
    return kb

def cancel_keyboard():
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("❌ إلغاء العملية")
    return kb

def back_keyboard():
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("🔙 رجوع")
    return kb

def get_correct_keyboard(user_id):
    is_admin = str(user_id) == ADMIN_ID
    return admin_keyboard() if is_admin else main_keyboard(False)

# ========== حالات (States) ==========
class CreateReport(StatesGroup):
    choose_region = State()
    choose_hospital = State()
    choose_department = State()
    choose_doctor = State()
    choose_gender = State()
    waiting_for_data = State()
    confirm = State()

class AddRegion(StatesGroup):
    name = State()

class DeleteRegion(StatesGroup):
    choose = State()

class AddHospital(StatesGroup):
    region = State()
    name = State()

class DeleteHospital(StatesGroup):
    choose = State()

class AddDepartment(StatesGroup):
    region = State()
    hospital = State()
    name = State()

class DeleteDepartment(StatesGroup):
    choose = State()

class AddDoctor(StatesGroup):
    region = State()
    hospital = State()
    department = State()
    name = State()
    title = State()
    pdf_male = State()
    pdf_female = State()

class DeleteDoctor(StatesGroup):
    choose = State()

class ManageTemplates(StatesGroup):
    choose_doctor = State()
    show_fields = State()
    select_required_data = State()
    confirm_settings = State()

class AddBalance(StatesGroup):
    user_id = State()
    amount = State()
    confirm_notify = State()

class DeductBalance(StatesGroup):
    user_id = State()
    amount = State()
    confirm_notify = State()

class BanUser(StatesGroup):
    user_id = State()

class UnbanUser(StatesGroup):
    user_id = State()

class InfoUser(StatesGroup):
    user_id = State()

class NotifyUser(StatesGroup):
    user_id = State()
    message = State()
    confirm = State()

class Broadcast(StatesGroup):
    message = State()
    confirm = State()

# ========== معالج الإلغاء ==========
@dp.message_handler(lambda m: m.text == "❌ إلغاء العملية", state="*")
async def cancel_operation(message: types.Message, state: FSMContext):
    if await state.get_state() is None:
        await message.answer("لا توجد عملية لإلغائها.")
        return
    await state.finish()
    await message.answer("✅ تم إلغاء العملية.", reply_markup=get_correct_keyboard(message.from_user.id))

# ========== بداية البوت ==========
@dp.message_handler(commands=['start'])
async def start(message: types.Message):
    user_id = message.from_user.id
    username = message.from_user.username or "NoUsername"
    is_admin = 1 if str(user_id) == ADMIN_ID else 0
    database.add_user(user_id, username, is_admin)
    await message.answer("🩺 أهلاً بك في نظام التقارير الطبية", reply_markup=main_keyboard(is_admin))

@dp.message_handler(lambda m: m.text == "ℹ️ الدعم")
async def support(message: types.Message):
    await message.answer("للتواصل مع الدعم: @SupportHandle", reply_markup=get_correct_keyboard(message.from_user.id))

@dp.message_handler(lambda m: m.text == "💰 رصيدي")
async def balance_handler(message: types.Message):
    user = database.get_user(message.from_user.id)
    if user and user[5] == 1:
        await message.answer("🚫 حسابك محظور.")
        return
    balance = database.get_balance(message.from_user.id)
    await message.answer(f"رصيدك الحالي: {balance} ريال", reply_markup=get_correct_keyboard(message.from_user.id))

# ========== إصدار تقرير (محدث) ==========
@dp.message_handler(lambda m: m.text == "🤍 إصدار إجازتك الآن")
async def start_report(message: types.Message):
    user_id = message.from_user.id
    user = database.get_user(user_id)
    if user and user[5] == 1:
        await message.answer("🚫 حسابك محظور.")
        return
    balance = database.get_balance(user_id)
    if float(balance) < 3.0:
        await message.answer("❌ رصيدك غير كافي.\nالرجاء إعادة الشحن لإصدار تقاريرك بنجاح ✅")
        return
    regions = database.get_regions()
    if not regions:
        await message.answer("لا توجد مناطق مسجلة حالياً، يرجى التواصل مع المطور.")
        return
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    for r in regions:
        kb.add(f"📍 {r[1]}")
    kb.add("🔙 رجوع")
    await message.answer("اختر المنطقة:", reply_markup=kb)
    await CreateReport.choose_region.set()

@dp.message_handler(state=CreateReport.choose_region)
async def choose_region(message: types.Message, state: FSMContext):
    if message.text == "🔙 رجوع":
        await state.finish()
        await message.answer("تم الإلغاء.", reply_markup=get_correct_keyboard(message.from_user.id))
        return
    region_name = message.text.replace("📍 ", "")
    regions = database.get_regions()
    region_id = None
    for r in regions:
        if r[1] == region_name:
            region_id = r[0]
            break
    if not region_id:
        await message.answer("❌ اختيار غير صحيح.")
        return
    hospitals = database.get_hospitals(region_id)
    if not hospitals:
        # لا توجد مستشفيات: نعيد عرض المناطق
        regions = database.get_regions()
        kb = ReplyKeyboardMarkup(resize_keyboard=True)
        for r in regions:
            kb.add(f"📍 {r[1]}")
        kb.add("🔙 رجوع")
        await message.answer("⚠️ لا توجد مستشفيات في هذه المنطقة حالياً. اختر منطقة أخرى:", reply_markup=kb)
        return
    await state.update_data(region_id=region_id, region_name=region_name)
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    for h in hospitals:
        kb.add(f"🏥 {h[2]} | ID:{h[0]}")
    kb.add("🔙 رجوع")
    await message.answer("اختر المستشفى:", reply_markup=kb)
    await CreateReport.choose_hospital.set()

@dp.message_handler(state=CreateReport.choose_hospital)
async def choose_hospital(message: types.Message, state: FSMContext):
    if message.text == "🔙 رجوع":
        regions = database.get_regions()
        kb = ReplyKeyboardMarkup(resize_keyboard=True)
        for r in regions:
            kb.add(f"📍 {r[1]}")
        kb.add("🔙 رجوع")
        await message.answer("اختر المنطقة:", reply_markup=kb)
        await CreateReport.choose_region.set()
        return
    # استخراج ID
    match = re.search(r'ID:(\d+)', message.text)
    if not match:
        await message.answer("❌ اختيار غير صحيح، يرجى المحاولة مرة أخرى.")
        return
    hospital_id = int(match.group(1))
    hospital = database.get_hospital(hospital_id)
    if not hospital:
        await message.answer("❌ المستشفى غير موجود.")
        return
    departments = database.get_departments(hospital_id)
    if not departments:
        await message.answer("⚠️ لا توجد أقسام في هذا المستشفى حالياً.")
        await state.finish()
        return
    await state.update_data(hospital_id=hospital_id, hospital_name=hospital[2])
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    for d in departments:
        kb.add(f"🩺 {d[2]} | ID:{d[0]}")
    kb.add("🔙 رجوع")
    await message.answer("اختر القسم:", reply_markup=kb)
    await CreateReport.choose_department.set()

@dp.message_handler(state=CreateReport.choose_department)
async def choose_department(message: types.Message, state: FSMContext):
    if message.text == "🔙 رجوع":
        data = await state.get_data()
        hospitals = database.get_hospitals(data["region_id"])
        kb = ReplyKeyboardMarkup(resize_keyboard=True)
        for h in hospitals:
            kb.add(f"🏥 {h[2]} | ID:{h[0]}")
        kb.add("🔙 رجوع")
        await message.answer("اختر المستشفى:", reply_markup=kb)
        await CreateReport.choose_hospital.set()
        return
    match = re.search(r'ID:(\d+)', message.text)
    if not match:
        await message.answer("❌ اختيار غير صحيح، يرجى المحاولة مرة أخرى.")
        return
    department_id = int(match.group(1))
    department = database.get_department(department_id)
    if not department:
        await message.answer("❌ القسم غير موجود.")
        return
    doctors = database.get_doctors(department_id)
    if not doctors:
        await message.answer("⚠️ لا يوجد أطباء في هذا القسم حالياً.")
        await state.finish()
        return
    await state.update_data(department_id=department_id, department_name=department[2])
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    for doc in doctors:
        kb.add(f"👨‍⚕️ {doc[3]} | ID:{doc[0]}")
    kb.add("🔙 رجوع")
    await message.answer("اختر الطبيب:", reply_markup=kb)
    await CreateReport.choose_doctor.set()

@dp.message_handler(state=CreateReport.choose_doctor)
async def choose_doctor(message: types.Message, state: FSMContext):
    if message.text == "🔙 رجوع":
        data = await state.get_data()
        departments = database.get_departments(data["hospital_id"])
        kb = ReplyKeyboardMarkup(resize_keyboard=True)
        for d in departments:
            kb.add(f"🩺 {d[2]} | ID:{d[0]}")
        kb.add("🔙 رجوع")
        await message.answer("اختر القسم:", reply_markup=kb)
        await CreateReport.choose_department.set()
        return
    match = re.search(r'ID:(\d+)', message.text)
    if not match:
        await message.answer("❌ اختيار غير صحيح، يرجى المحاولة مرة أخرى.")
        return
    doctor_id = int(match.group(1))
    doctor = database.get_doctor(doctor_id)
    if not doctor:
        await message.answer("❌ الطبيب غير موجود.")
        return
    # التحقق من وجود قوالب
    if not doctor_has_templates(doctor_id):
        await message.answer("⚠️ هذا الطبيب لم يتم إعداد قوالب التقارير له بعد. يرجى التواصل مع الإدارة.")
        return
    await state.update_data(doctor_id=doctor_id, doctor_name=doctor[3],
                            template_male=doctor[4], template_female=doctor[5])
    # اختيار الجنس
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("👨 ذكر", "👩 أنثى")
    kb.add("🔙 رجوع")
    await message.answer("اختر جنس المريض:", reply_markup=kb)
    await CreateReport.choose_gender.set()

@dp.message_handler(state=CreateReport.choose_gender)
async def choose_gender(message: types.Message, state: FSMContext):
    if message.text == "🔙 رجوع":
        data = await state.get_data()
        doctors = database.get_doctors(data["department_id"])
        kb = ReplyKeyboardMarkup(resize_keyboard=True)
        for doc in doctors:
            kb.add(f"👨‍⚕️ {doc[3]} | ID:{doc[0]}")
        kb.add("🔙 رجوع")
        await message.answer("اختر الطبيب:", reply_markup=kb)
        await CreateReport.choose_doctor.set()
        return
    gender_map = {"👨 ذكر": "ذكر", "👩 أنثى": "أنثى"}
    if message.text not in gender_map:
        await message.answer("❌ اختيار غير صحيح.")
        return
    gender = gender_map[message.text]
    await state.update_data(gender=gender)

    # الحصول على البيانات المطلوبة لهذا الطبيب
    data = await state.get_data()
    doctor_id = data["doctor_id"]
    required_keys = database.get_required_data(doctor_id)
    if not required_keys:
        # إذا لم يحدد المطور أي بيانات مطلوبة، نستخدم مجموعة افتراضية
        required_keys = ["full_name", "birth_date", "employer", "nationality", "start_date", "leave_days"]
    await state.update_data(required_keys=required_keys, current_data={})
    # بدء طلب البيانات
    await ask_next_required_data(message, state)

async def ask_next_required_data(message: types.Message, state: FSMContext):
    data = await state.get_data()
    required = data.get("required_keys", [])
    collected = data.get("current_data", {})
    for key in required:
        if key not in collected:
            prompt = get_prompt_for_key(key)
            await message.answer(prompt, reply_markup=cancel_keyboard())
            await state.update_data(current_key=key)
            await CreateReport.waiting_for_data.set()
            return
    # إذا تم جمع كل شيء، نعرض الملخص
    await show_summary_and_confirm(message, state)

def get_prompt_for_key(key):
    prompts = {
        "full_name": "أدخل الاسم الكامل (بالعربية):",
        "birth_date": "أدخل تاريخ الميلاد (YYYY-MM-DD):",
        "employer": "أدخل جهة العمل:",
        "nationality": "أدخل الجنسية:",
        "start_date": "أدخل تاريخ بداية الإجازة (YYYY-MM-DD):",
        "leave_days": "أدخل عدد أيام الإجازة:",
        "age": "أدخل العمر (اختياري إذا لم تدخل تاريخ الميلاد):",
        "file_no": "رقم الملف (سيتم توليده تلقائياً)",
    }
    return prompts.get(key, f"أدخل {key}:")

@dp.message_handler(state=CreateReport.waiting_for_data)
async def handle_required_data(message: types.Message, state: FSMContext):
    if message.text == "❌ إلغاء العملية":
        await cancel_operation(message, state)
        return
    data = await state.get_data()
    current_key = data.get("current_key")
    collected = data.get("current_data", {})

    # التحقق من صحة الإدخال
    if current_key in ["birth_date", "start_date"]:
        if not validate_date(message.text):
            await message.answer("❌ صيغة تاريخ غير صحيحة. استخدم YYYY-MM-DD (مثال: 2026-02-04)")
            return
    elif current_key == "leave_days":
        if not message.text.isdigit() or int(message.text) <= 0:
            await message.answer("❌ الرجاء إدخال رقم صحيح أكبر من 0")
            return
    elif current_key == "age":
        if message.text and not message.text.isdigit():
            await message.answer("❌ الرجاء إدخال رقم صحيح للعمر")
            return

    collected[current_key] = message.text
    await state.update_data(current_data=collected)
    await ask_next_required_data(message, state)

async def show_summary_and_confirm(message: types.Message, state: FSMContext):
    data = await state.get_data()
    collected = data.get("current_data", {})
    lines = ["📋 ملخص البيانات:"]
    for key, value in collected.items():
        lines.append(f"• {key}: {value}")
    lines.append("هل البيانات صحيحة؟")
    kb = yes_no_keyboard()
    kb.add("❌ إلغاء العملية")
    await message.answer("\n".join(lines), reply_markup=kb)
    await CreateReport.confirm.set()

@dp.message_handler(state=CreateReport.confirm)
async def confirm_report(message: types.Message, state: FSMContext):
    if message.text == "❌ إلغاء العملية":
        await cancel_operation(message, state)
        return
    if message.text != "✅ نعم":
        await message.answer("تم الإلغاء.", reply_markup=get_correct_keyboard(message.from_user.id))
        await state.finish()
        return

    data = await state.get_data()
    user_id = message.from_user.id
    collected = data.get("current_data", {})

    # --- معالجة البيانات المحسوبة ---
    if "start_date" in collected:
        start_date_obj = datetime.strptime(collected["start_date"], "%Y-%m-%d").date()
    else:
        start_date_obj = date.today()
    file_no = generate_file_no(start_date_obj)

    age = None
    if "birth_date" in collected:
        birth = datetime.strptime(collected["birth_date"], "%Y-%m-%d").date()
        age = calculate_age(birth)
    elif "age" in collected:
        age = int(collected["age"])

    nationality_ar = collected.get("nationality", "سعودي")
    nationality_en = translate_arabic_to_english(nationality_ar)

    employer_ar = collected.get("employer", "")
    employer_en = translate_arabic_to_english(employer_ar)

    if "start_date" in collected:
        start_date = datetime.strptime(collected["start_date"], "%Y-%m-%d").date()
        leave_days = int(collected.get("leave_days", 1))
        end_date = start_date + timedelta(days=leave_days - 1)
        start_hijri = gregorian_to_hijri(start_date)
        end_hijri = gregorian_to_hijri(end_date)
        start_greg = start_date.strftime("%d-%m-%Y")
        end_greg = end_date.strftime("%d-%m-%Y")
    else:
        start_hijri = end_hijri = ""
        start_greg = end_greg = ""

    # --- تجهيز بيانات الحقول ---
    field_data = {}
    field_data["full_name_ar"] = collected.get("full_name", "")
    field_data["full_name_en"] = translate_arabic_to_english(field_data["full_name_ar"])
    field_data["file_no"] = file_no
    if age:
        field_data["age"] = str(age)
    field_data["nationality_ar"] = nationality_ar
    field_data["nationality_en"] = nationality_en
    field_data["employer_ar"] = employer_ar
    field_data["employer_en"] = employer_en
    field_data["clinic_date_ar"] = start_hijri
    field_data["clinic_date_en"] = start_greg
    field_data["admission_date_ar"] = start_hijri
    field_data["admission_date_en"] = start_greg
    field_data["discharge_date_ar"] = end_hijri
    field_data["discharge_date_en"] = end_greg
    field_data["leave_days"] = str(leave_days) if 'leave_days' in locals() else ""
    field_data["from_date_h"] = start_hijri
    field_data["to_date_h"] = end_hijri
    field_data["from_date_g"] = start_greg
    field_data["to_date_g"] = end_greg
    if data["gender"] == "ذكر":
        field_data["male_checkbox"] = "Yes"
    else:
        field_data["female_checkbox"] = "Yes"

    # --- اختيار القالب ---
    template_path = data["template_male"] if data["gender"] == "ذكر" else data["template_female"]

    # --- تعبئة PDF مع معالجة الأخطاء ---
    output_stream = io.BytesIO()
    try:
        fill_pdf_form(template_path, output_stream, field_data)
        output_stream.seek(0)
    except Exception as e:
        logging.error(f"Error filling PDF for doctor {data['doctor_id']}: {e}")
        await message.answer("❌ حدث خطأ أثناء إنشاء التقرير. تم إبلاغ المطور.")
        # إرسال تقرير الخطأ للمطور
        await bot.send_message(ADMIN_ID, f"خطأ في تعبئة PDF للطبيب {data['doctor_id']}: {e}")
        await state.finish()
        return

    # --- خصم الرصيد وحفظ التقرير ---
    database.update_balance(user_id, -3, "report")
    database.save_report(user_id, data["doctor_id"], collected.get("full_name", ""), data["gender"])

    # --- إرسال الملف ---
    await bot.send_document(user_id, InputFile(output_stream, filename="تقرير_طبي.pdf"))

    # --- فحص الرصيد المنخفض ---
    await check_low_balance(user_id)

    await message.answer("✅ تم إنشاء التقرير بنجاح.", reply_markup=get_correct_keyboard(user_id))
    await state.finish()

async def check_low_balance(user_id):
    balance = database.get_balance(user_id)
    if balance < 3:
        try:
            await bot.send_message(user_id, "⚠ رصيدك أوشك على الانتهاء.\nالرجاء إعادة الشحن لإصدار تقاريرك بنجاح ✅")
        except:
            pass

# ========== لوحة المطور ==========
@dp.message_handler(lambda m: m.text == "👑 لوحة المطور")
async def admin_panel(message: types.Message):
    if str(message.from_user.id) != ADMIN_ID:
        return
    await message.answer("👑 لوحة التحكم", reply_markup=admin_keyboard())

# ========== إدارة الرصيد (كما هي) ==========
@dp.message_handler(lambda m: m.text == "💰 إدارة الرصيد")
async def balance_management(message: types.Message):
    if str(message.from_user.id) != ADMIN_ID:
        return
    await message.answer("إدارة الرصيد:", reply_markup=balance_management_keyboard())

# (سيتم إدراج معالجات إدارة الرصيد هنا، وهي مطابقة للإصدار السابق، ولكن للاختصار لم أكررها. في الكود الفعلي يجب تضمينها.)

# ========== إدارة المناطق والمستشفيات والأقسام (كما هي) ==========
# (تم تضمينها في الإصدار السابق، وسأعيد استخدامها. للاختصار لم أكررها هنا، ولكن في الكود الفعلي يجب تضمين جميع المعالجات.)

# ========== إدارة الأطباء (محدثة) ==========
@dp.message_handler(lambda m: m.text == "👨‍⚕️ إدارة الأطباء")
async def manage_doctors_menu(message: types.Message):
    if str(message.from_user.id) != ADMIN_ID:
        return
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("👨‍⚕️ عرض الأطباء", "➕ إضافة طبيب", "🗑 حذف طبيب")
    kb.add("🔙 رجوع")
    await message.answer("إدارة الأطباء:", reply_markup=kb)

@dp.message_handler(lambda m: m.text == "👨‍⚕️ عرض الأطباء")
async def list_doctors(message: types.Message):
    if str(message.from_user.id) != ADMIN_ID:
        return
    doctors = database.get_doctors()
    if not doctors:
        await message.answer("لا يوجد أطباء مسجلين.", reply_markup=admin_keyboard())
        return
    text = "الأطباء المسجلون:\n\n"
    for doc in doctors:
        text += f"🆔 {doc[0]} | {doc[3]} - {doc[4]}\n"
    await message.answer(text, reply_markup=admin_keyboard())

@dp.message_handler(lambda m: m.text == "➕ إضافة طبيب")
async def add_doctor_start(message: types.Message):
    if str(message.from_user.id) != ADMIN_ID:
        return
    regions = database.get_regions()
    if not regions:
        await message.answer("يجب إضافة منطقة أولاً.", reply_markup=admin_keyboard())
        return
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    for r in regions:
        kb.add(f"📍 {r[1]} | ID:{r[0]}")
    kb.add("🔙 رجوع")
    await message.answer("اختر المنطقة:", reply_markup=kb)
    await AddDoctor.region.set()

@dp.message_handler(state=AddDoctor.region)
async def add_doctor_region(message: types.Message, state: FSMContext):
    if message.text == "🔙 رجوع":
        await manage_doctors_menu(message)
        await state.finish()
        return
    match = re.search(r'ID:(\d+)', message.text)
    if not match:
        await message.answer("❌ منطقة غير صحيحة.")
        return
    region_id = int(match.group(1))
    region = database.get_region(region_id)
    if not region:
        await message.answer("❌ منطقة غير صحيحة.")
        return
    await state.update_data(region_id=region_id, region_name=region[1])
    hospitals = database.get_hospitals(region_id)
    if not hospitals:
        await message.answer("لا توجد مستشفيات في هذه المنطقة.")
        await state.finish()
        return
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    for h in hospitals:
        kb.add(f"🏥 {h[2]} | ID:{h[0]}")
    kb.add("🔙 رجوع")
    await message.answer("اختر المستشفى:", reply_markup=kb)
    await AddDoctor.hospital.set()

@dp.message_handler(state=AddDoctor.hospital)
async def add_doctor_hospital(message: types.Message, state: FSMContext):
    if message.text == "🔙 رجوع":
        await manage_doctors_menu(message)
        await state.finish()
        return
    match = re.search(r'ID:(\d+)', message.text)
    if not match:
        await message.answer("❌ مستشفى غير صحيح.")
        return
    hospital_id = int(match.group(1))
    hospital = database.get_hospital(hospital_id)
    if not hospital:
        await message.answer("❌ مستشفى غير صحيح.")
        return
    await state.update_data(hospital_id=hospital_id, hospital_name=hospital[2])
    departments = database.get_departments(hospital_id)
    if not departments:
        await message.answer("لا توجد أقسام في هذا المستشفى.")
        await state.finish()
        return
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    for d in departments:
        kb.add(f"🩺 {d[2]} | ID:{d[0]}")
    kb.add("🔙 رجوع")
    await message.answer("اختر القسم:", reply_markup=kb)
    await AddDoctor.department.set()

@dp.message_handler(state=AddDoctor.department)
async def add_doctor_department(message: types.Message, state: FSMContext):
    if message.text == "🔙 رجوع":
        await manage_doctors_menu(message)
        await state.finish()
        return
    match = re.search(r'ID:(\d+)', message.text)
    if not match:
        await message.answer("❌ قسم غير صحيح.")
        return
    department_id = int(match.group(1))
    department = database.get_department(department_id)
    if not department:
        await message.answer("❌ قسم غير صحيح.")
        return
    await state.update_data(department_id=department_id, department_name=department[2])
    await message.answer("أرسل اسم الطبيب:", reply_markup=cancel_keyboard())
    await AddDoctor.name.set()

@dp.message_handler(state=AddDoctor.name)
async def add_doctor_name(message: types.Message, state: FSMContext):
    if message.text == "❌ إلغاء العملية":
        await cancel_operation(message, state)
        return
    name = message.text.strip()
    if not name:
        await message.answer("❌ اسم غير صالح.")
        return
    await state.update_data(name=name)
    await message.answer("أرسل المسمى الوظيفي (مثل: استشاري باطنية):", reply_markup=cancel_keyboard())
    await AddDoctor.title.set()

@dp.message_handler(state=AddDoctor.title)
async def add_doctor_title(message: types.Message, state: FSMContext):
    if message.text == "❌ إلغاء العملية":
        await cancel_operation(message, state)
        return
    title = message.text.strip()
    if not title:
        await message.answer("❌ مسمى غير صالح.")
        return
    await state.update_data(title=title)
    await message.answer("الرجاء رفع ملف PDF الخاص بالمرضى الذكور:", reply_markup=cancel_keyboard())
    await AddDoctor.pdf_male.set()

@dp.message_handler(content_types=['document'], state=AddDoctor.pdf_male)
async def add_doctor_pdf_male(message: types.Message, state: FSMContext):
    if message.text == "❌ إلغاء العملية":
        await cancel_operation(message, state)
        return
    if not message.document or not message.document.file_name.endswith('.pdf'):
        await message.answer("❌ يرجى رفع ملف PDF صالح.")
        return
    file_id = message.document.file_id
    await state.update_data(pdf_male_id=file_id)
    await message.answer("تم استلام ملف الذكور. الآن رفع ملف PDF الخاص بالمرضى الإناث:", reply_markup=cancel_keyboard())
    await AddDoctor.pdf_female.set()

@dp.message_handler(content_types=['document'], state=AddDoctor.pdf_female)
async def add_doctor_pdf_female(message: types.Message, state: FSMContext):
    if message.text == "❌ إلغاء العملية":
        await cancel_operation(message, state)
        return
    if not message.document or not message.document.file_name.endswith('.pdf'):
        await message.answer("❌ يرجى رفع ملف PDF صالح.")
        return
    file_id_female = message.document.file_id
    data = await state.get_data()

    # تحميل الملفات
    male_file_id = data["pdf_male_id"]
    male_file_info = await bot.get_file(male_file_id)
    male_bytes = await bot.download_file(male_file_info.file_path)
    female_file_info = await bot.get_file(file_id_female)
    female_bytes = await bot.download_file(female_file_info.file_path)

    # حفظها محلياً
    region_name = data["region_name"]
    hospital_name = data["hospital_name"]
    department_name = data["department_name"]

    male_path = get_template_path(region_name, hospital_name, department_name, "male")
    female_path = get_template_path(region_name, hospital_name, department_name, "female")

    with open(male_path, "wb") as f:
        f.write(male_bytes.getvalue())
    with open(female_path, "wb") as f:
        f.write(female_bytes.getvalue())

    # التحقق من احتواء الملفات على حقول
    try:
        fields_male = extract_form_fields(male_path)
        fields_female = extract_form_fields(female_path)
    except Exception as e:
        await message.answer(f"❌ الملف لا يحتوي على حقول تعبئة: {e}")
        return

    # إضافة الطبيب
    doctor_id = database.add_doctor(
        data["department_id"],
        data["name"],
        data["title"],
        male_path,
        female_path
    )

    # حفظ الحقول
    all_fields = set(fields_male + fields_female)
    database.set_template_fields(doctor_id, list(all_fields))

    # تعيين مجموعة افتراضية من البيانات المطلوبة
    default_required = ["full_name", "birth_date", "employer", "nationality", "start_date", "leave_days"]
    database.set_required_data(doctor_id, default_required)

    await message.answer(f"✅ تم إضافة الطبيب '{data['name']}' بنجاح مع القوالب.", reply_markup=admin_keyboard())
    await state.finish()

@dp.message_handler(lambda m: m.text == "🗑 حذف طبيب")
async def delete_doctor_start(message: types.Message):
    if str(message.from_user.id) != ADMIN_ID:
        return
    doctors = database.get_doctors()
    if not doctors:
        await message.answer("لا يوجد أطباء مسجلين.", reply_markup=admin_keyboard())
        return
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    for doc in doctors:
        kb.add(f"🗑 {doc[3]} | ID:{doc[0]}")
    kb.add("🔙 رجوع")
    await message.answer("اختر الطبيب للحذف:", reply_markup=kb)
    await DeleteDoctor.choose.set()

@dp.message_handler(state=DeleteDoctor.choose)
async def delete_doctor_execute(message: types.Message, state: FSMContext):
    if message.text == "🔙 رجوع":
        await manage_doctors_menu(message)
        await state.finish()
        return
    match = re.search(r'ID:(\d+)', message.text)
    if not match:
        await message.answer("❌ طبيب غير صحيح.")
        return
    doctor_id = int(match.group(1))
    database.delete_doctor(doctor_id)
    await message.answer(f"✅ تم حذف الطبيب.", reply_markup=admin_keyboard())
    await state.finish()

# ========== إعداد وتعديل نظام التقارير ==========
@dp.message_handler(lambda m: m.text == "🛠 إعداد وتعديل نظام التقارير")
async def manage_templates_menu(message: types.Message):
    if str(message.from_user.id) != ADMIN_ID:
        return
    doctors = database.get_doctors()
    if not doctors:
        await message.answer("لا يوجد أطباء مسجلين.", reply_markup=admin_keyboard())
        return
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    for doc in doctors:
        kb.add(f"🔧 {doc[3]} | ID:{doc[0]}")
    kb.add("🔙 رجوع")
    await message.answer("اختر الطبيب لتعديل إعدادات تقاريره:", reply_markup=kb)
    await ManageTemplates.choose_doctor.set()

@dp.message_handler(state=ManageTemplates.choose_doctor)
async def choose_doctor_for_template(message: types.Message, state: FSMContext):
    if message.text == "🔙 رجوع":
        await admin_panel(message)
        await state.finish()
        return
    match = re.search(r'ID:(\d+)', message.text)
    if not match:
        await message.answer("❌ طبيب غير صحيح.")
        return
    doctor_id = int(match.group(1))
    doctor = database.get_doctor(doctor_id)
    if not doctor:
        await message.answer("❌ طبيب غير موجود.")
        return
    await state.update_data(doctor_id=doctor_id)

    # عرض الحقول الموجودة
    fields = database.get_template_fields(doctor_id)
    if not fields:
        await message.answer("لا توجد حقول مسجلة لهذا الطبيب. ربما لم يتم رفع القوالب بعد.")
        await state.finish()
        return

    field_list = "\n".join(fields)
    await message.answer(
        f"الحقول المتوفرة في قوالب هذا الطبيب:\n{field_list}\n\n"
        "أرسل أسماء الحقول التي تريد تعبئتها (مفصولة بفواصل)، أو أرسل 'الكل' لاختيار الكل.",
        reply_markup=cancel_keyboard()
    )
    await ManageTemplates.show_fields.set()

@dp.message_handler(state=ManageTemplates.show_fields)
async def select_fields(message: types.Message, state: FSMContext):
    if message.text == "❌ إلغاء العملية":
        await cancel_operation(message, state)
        return
    data = await state.get_data()
    doctor_id = data["doctor_id"]
    all_fields = database.get_template_fields(doctor_id)

    if message.text == "الكل":
        selected = all_fields
    else:
        parts = [p.strip() for p in message.text.split(',')]
        selected = [p for p in parts if p in all_fields]

    if not selected:
        await message.answer("لم تختار أي حقل صحيح. حاول مرة أخرى.")
        return

    database.set_template_fields(doctor_id, selected)

    # اختيار البيانات المطلوب جمعها
    possible_data = [
        "full_name", "birth_date", "employer", "nationality",
        "start_date", "leave_days", "age", "file_no"
    ]
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    for item in possible_data:
        kb.add(f"📌 {item}")
    kb.add("✅ انتهيت")
    kb.add("❌ إلغاء العملية")
    await message.answer(
        "اختر البيانات التي تريد أن يطلبها النظام من المستخدم (اضغط على كل عنصر، ثم انتهيت):",
        reply_markup=kb
    )
    await state.update_data(selected_data=[])
    await ManageTemplates.select_required_data.set()

@dp.message_handler(state=ManageTemplates.select_required_data)
async def select_required_data(message: types.Message, state: FSMContext):
    if message.text == "❌ إلغاء العملية":
        await cancel_operation(message, state)
        return
    if message.text == "✅ انتهيت":
        data = await state.get_data()
        selected = data.get("selected_data", [])
        doctor_id = data["doctor_id"]
        database.set_required_data(doctor_id, selected)
        await message.answer("✅ تم حفظ إعدادات التقرير.", reply_markup=admin_keyboard())
        await state.finish()
        return
    item = message.text.replace("📌 ", "")
    if item in ["full_name", "birth_date", "employer", "nationality", "start_date", "leave_days", "age", "file_no"]:
        data = await state.get_data()
        selected = data.get("selected_data", [])
        if item not in selected:
            selected.append(item)
            await state.update_data(selected_data=selected)
            await message.answer(f"✅ تمت إضافة {item}. يمكنك اختيار المزيد أو الضغط على 'انتهيت'.")
        else:
            await message.answer(f"❗ {item} مضاف بالفعل.")
    else:
        await message.answer("❌ اختيار غير صحيح.")

# ========== الإحصائيات ==========
@dp.message_handler(lambda m: m.text == "📊 الإحصائيات")
async def stats(message: types.Message):
    if str(message.from_user.id) != ADMIN_ID:
        return
    stats = database.get_report_stats()
    text = (
        f"📊 إحصائيات عامة:\n\n"
        f"📄 عدد التقارير المنشأة: {stats['total_reports']}\n"
        f"💰 إجمالي الأرباح: {stats['total_income']} ريال\n"
    )
    if stats['top_hospital']:
        text += f"🏥 أكثر مستشفى إصداراً: {stats['top_hospital'][0]} ({stats['top_hospital'][1]} تقرير)\n"
    if stats['top_doctor']:
        text += f"👨‍⚕️ أكثر طبيب إصداراً: {stats['top_doctor'][0]} ({stats['top_doctor'][1]} تقرير)\n"
    await message.answer(text, reply_markup=admin_keyboard())

# ========== الإشعارات ==========
@dp.message_handler(lambda m: m.text == "📢 الإشعارات")
async def notifications_menu(message: types.Message):
    if str(message.from_user.id) != ADMIN_ID:
        return
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("📢 إشعار لمستخدم", "📣 إشعار جماعي")
    kb.add("🔙 رجوع")
    await message.answer("الإشعارات:", reply_markup=kb)

# (معالجات الإشعارات كما هي، للاختصار لم أكررها)

# ========== العودة للقائمة الرئيسية ==========
@dp.message_handler(lambda m: m.text == "🔙 رجوع", state="*")
async def back_main(message: types.Message, state: FSMContext):
    if await state.get_state() is not None:
        await state.finish()
        await message.answer("❌ تم إلغاء العملية للرجوع.")
    is_admin = str(message.from_user.id) == ADMIN_ID
    await message.answer("القائمة الرئيسية", reply_markup=main_keyboard(is_admin))

if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True)
