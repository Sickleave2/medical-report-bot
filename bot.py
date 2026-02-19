import logging
import os
import io
import json
import random
import re
import fitz  # PyMuPDF
from datetime import datetime, timedelta, date
from dateutil.relativedelta import relativedelta
from hijri_converter import Gregorian
from unidecode import unidecode
from deep_translator import GoogleTranslator
from aiogram import Bot, Dispatcher, executor, types
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InputFile
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.contrib.fsm_storage.memory import MemoryStorage
import database

# ========== التحقق من وجود ADMIN_ID ==========
ADMIN_ID = os.getenv("ADMIN_ID")
if not ADMIN_ID:
    raise ValueError("❌ ADMIN_ID is not set in environment variables")
ADMIN_ID = ADMIN_ID.strip()

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("❌ BOT_TOKEN is not set in environment variables")

logging.basicConfig(level=logging.INFO)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot, storage=MemoryStorage())

TEMPLATES_DIR = "templates"
os.makedirs(TEMPLATES_DIR, exist_ok=True)

database.init_db()
database.seed_regions()

# ========== دوال مساعدة ==========
def transliterate_arabic(text):
    """تحويل النص العربي إلى حروف لاتينية (تقريبي)"""
    return unidecode(text)

def translate_ar_to_en(text):
    """ترجمة من العربية إلى الإنجليزية مع fallback"""
    try:
        return GoogleTranslator(source='ar', target='en').translate(text)
    except Exception as e:
        logging.warning(f"Translation failed, using unidecode: {e}")
        return transliterate_arabic(text)

def gregorian_to_hijri_str(greg_date):
    """تحويل تاريخ ميلادي إلى سلسلة هجرية YYYY-MM-DD"""
    h = Gregorian.fromdate(greg_date).to_hijri()
    return f"{h.year}-{h.month:02d}-{h.day:02d}"

def generate_file_no(start_date):
    """توليد رقم ملف: YYMMDD + 3 أرقام عشوائية"""
    yymmdd = start_date.strftime("%y%m%d")
    rand = f"{random.randint(100, 999)}"
    return yymmdd + rand

def calculate_age(birth_date):
    """حساب العمر من تاريخ الميلاد"""
    today = date.today()
    return today.year - birth_date.year - ((today.month, today.day) < (birth_date.month, birth_date.day))

def validate_date(date_str):
    """التحقق من صحة التاريخ"""
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        return None

def validate_positive_int(value_str, max_val=30):
    """التحقق من أن القيمة رقم صحيح موجب وأقل من حد معين"""
    try:
        val = int(value_str)
        if 1 <= val <= max_val:
            return val
        return None
    except ValueError:
        return None

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

def templates_management_keyboard():
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("📄 إدارة القوالب", "🧩 إدارة الحقول")
    kb.add("📋 تحديد البيانات المطلوبة", "🔄 تعديل قالب")
    kb.add("🗑 حذف قالب", "💾 حفظ التكوين")
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
    dynamic_fields = State()
    confirm = State()

class ManageTemplates(StatesGroup):
    choose_doctor = State()
    upload_male = State()
    upload_female = State()
    select_fields_to_fill = State()
    select_user_fields = State()

class EditTemplate(StatesGroup):
    choose_doctor = State()
    action = State()

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

class DeleteDoctor(StatesGroup):
    choose = State()

# ========== معالج الأخطاء العام ==========
@dp.errors_handler()
async def global_error_handler(update: types.Update, exception: Exception):
    logging.exception(f"Unhandled error: {exception}")
    try:
        if update.message:
            await update.message.answer("❌ حدث خطأ داخلي. يرجى المحاولة لاحقاً.")
    except:
        pass
    return True

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
        regions = database.get_regions()
        kb = ReplyKeyboardMarkup(resize_keyboard=True)
        for r in regions:
            kb.add(f"📍 {r[1]}")
        kb.add("🔙 رجوع")
        await message.answer("⚠️ لا توجد مستشفيات في هذه المنطقة حالياً. اختر منطقة أخرى:", reply_markup=kb)
        return
    await state.update_data(region_id=region_id)
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    for h in hospitals:
        kb.add(f"🏥 {h[2]}")
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
    hospital_name = message.text.replace("🏥 ", "")
    data = await state.get_data()
    hospitals = database.get_hospitals(data["region_id"])
    hospital_id = None
    for h in hospitals:
        if h[2] == hospital_name:
            hospital_id = h[0]
            break
    if not hospital_id:
        await message.answer("❌ اختيار غير صحيح.")
        return
    departments = database.get_departments(hospital_id)
    if not departments:
        await message.answer("⚠️ لا توجد أقسام في هذا المستشفى حالياً.")
        await state.finish()
        return
    await state.update_data(hospital_id=hospital_id, hospital_name=hospital_name)
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    for d in departments:
        kb.add(f"🩺 {d[2]}")
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
            kb.add(f"🏥 {h[2]}")
        kb.add("🔙 رجوع")
        await message.answer("اختر المستشفى:", reply_markup=kb)
        await CreateReport.choose_hospital.set()
        return
    department_name = message.text.replace("🩺 ", "")
    data = await state.get_data()
    departments = database.get_departments(data["hospital_id"])
    department_id = None
    for d in departments:
        if d[2] == department_name:
            department_id = d[0]
            break
    if not department_id:
        await message.answer("❌ اختيار غير صحيح.")
        return
    doctors = database.get_doctors(department_id)
    if not doctors:
        await message.answer("⚠️ لا يوجد أطباء في هذا القسم حالياً.")
        await state.finish()
        return
    await state.update_data(department_id=department_id)
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    for doc in doctors:
        kb.add(f"👨‍⚕️ {doc[3]}")
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
            kb.add(f"🩺 {d[2]}")
        kb.add("🔙 رجوع")
        await message.answer("اختر القسم:", reply_markup=kb)
        await CreateReport.choose_department.set()
        return
    doctor_name = message.text.replace("👨‍⚕️ ", "")
    data = await state.get_data()
    doctors = database.get_doctors(data["department_id"])
    doctor_id = None
    for doc in doctors:
        if doc[3] == doctor_name:
            doctor_id = doc[0]
            break
    if not doctor_id:
        await message.answer("❌ اختيار غير صحيح.")
        return
    # التحقق من وجود تكوين قالب
    template = database.get_template_config(doctor_id)
    if not template:
        await message.answer("⚠️ لم يتم إعداد قالب تقرير لهذا الطبيب بعد. يرجى التواصل مع المطور.")
        await state.finish()
        return
    await state.update_data(doctor_id=doctor_id, doctor_name=doctor_name, template=template)
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
            kb.add(f"👨‍⚕️ {doc[3]}")
        kb.add("🔙 رجوع")
        await message.answer("اختر الطبيب:", reply_markup=kb)
        await CreateReport.choose_doctor.set()
        return
    gender_map = {"👨 ذكر": "ذكر", "👩 أنثى": "أنثى"}
    if message.text not in gender_map:
        await message.answer("❌ اختيار غير صحيح.")
        return
    gender = gender_map[message.text]
    data = await state.get_data()
    template = data['template']
    user_fields = template['user_fields']

    if not user_fields:
        # حقول افتراضية
        user_fields = ["full_name_ar", "birth_date", "employer", "nationality", "leave_days"]
        await state.update_data(user_fields=user_fields)

    await state.update_data(gender=gender, answers={}, current_field_index=0, user_fields=user_fields)
    await ask_next_field(message, state)

async def ask_next_field(message: types.Message, state: FSMContext):
    data = await state.get_data()
    user_fields = data['user_fields']
    index = data.get('current_field_index', 0)
    if index >= len(user_fields):
        await show_summary(message, state)
        return

    field_name = user_fields[index]
    prompts = {
        "full_name_ar": "أدخل الاسم الكامل (بالعربية):",
        "full_name_en": "أدخل الاسم الكامل (بالإنجليزية):",
        "birth_date": "أدخل تاريخ الميلاد (YYYY-MM-DD):",
        "employer": "أدخل جهة العمل:",
        "nationality": "أدخل الجنسية:",
        "leave_days": "أدخل عدد أيام الإجازة:",
        "start_date": "أدخل تاريخ بداية الإجازة (YYYY-MM-DD):",
    }
    prompt = prompts.get(field_name, f"أدخل قيمة {field_name}:")
    await message.answer(prompt, reply_markup=cancel_keyboard())
    await CreateReport.dynamic_fields.set()

@dp.message_handler(state=CreateReport.dynamic_fields)
async def handle_dynamic_field(message: types.Message, state: FSMContext):
    if message.text == "❌ إلغاء العملية":
        await cancel_operation(message, state)
        return
    data = await state.get_data()
    user_fields = data['user_fields']
    index = data['current_field_index']
    field_name = user_fields[index]
    answers = data.get('answers', {})

    # التحقق من صحة المدخلات حسب نوع الحقل
    valid = True
    value = message.text
    if field_name == "birth_date":
        if not validate_date(value):
            await message.answer("❌ صيغة تاريخ غير صحيحة. استخدم YYYY-MM-DD")
            valid = False
    elif field_name == "leave_days":
        days = validate_positive_int(value, 30)
        if days is None:
            await message.answer("❌ عدد الأيام يجب أن يكون رقماً بين 1 و 30")
            valid = False
        else:
            value = days  # نحتفظ بالقيمة الرقمية
    # يمكن إضافة المزيد من التحقق حسب الحاجة

    if not valid:
        return  # نبقى في نفس الحالة

    answers[field_name] = value
    await state.update_data(answers=answers, current_field_index=index+1)
    await ask_next_field(message, state)

async def show_summary(message: types.Message, state: FSMContext):
    data = await state.get_data()
    answers = data['answers']
    summary_lines = ["📋 ملخص البيانات:"]
    for k, v in answers.items():
        summary_lines.append(f"{k}: {v}")
    summary_lines.append("\nهل البيانات صحيحة؟")
    kb = yes_no_keyboard()
    kb.add("❌ إلغاء العملية")
    await message.answer("\n".join(summary_lines), reply_markup=kb)
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
    answers = data['answers']
    user_id = message.from_user.id
    gender = data['gender']
    doctor_id = data['doctor_id']
    template = data['template']

    # --- تحضير البيانات المحسوبة مع معالجة الأخطاء ---
    try:
        # تاريخ بداية الإجازة
        start_date_str = answers.get('start_date')
        if start_date_str:
            start_date = validate_date(start_date_str)
            if not start_date:
                raise ValueError("Invalid start date")
        else:
            start_date = date.today()

        # رقم الملف
        file_no = generate_file_no(start_date)

        # العمر
        birth_date_str = answers.get('birth_date')
        age = None
        if birth_date_str:
            birth_date = validate_date(birth_date_str)
            if birth_date:
                age = calculate_age(birth_date)
            else:
                raise ValueError("Invalid birth date")
        else:
            age = answers.get('age', '')

        # عدد الأيام
        leave_days = int(answers.get('leave_days', 1))

        # ترجمة النصوص
        name_ar = answers.get('full_name_ar', '')
        name_en = answers.get('full_name_en', '')
        if name_ar and not name_en:
            name_en = translate_ar_to_en(name_ar)

        employer_ar = answers.get('employer', '')
        employer_en = answers.get('employer_en', '')
        if employer_ar and not employer_en:
            employer_en = translate_ar_to_en(employer_ar)

        nationality_ar = answers.get('nationality', '')
        nationality_en = answers.get('nationality_en', '')
        if nationality_ar and not nationality_en:
            nationality_en = translate_ar_to_en(nationality_ar)

        # التواريخ
        clinic_date = start_date
        discharge_date = start_date + timedelta(days=leave_days - 1)
        clinic_date_hijri = gregorian_to_hijri_str(clinic_date)
        discharge_date_hijri = gregorian_to_hijri_str(discharge_date)

        fill_values = {
            'full_name_ar': name_ar,
            'full_name_en': name_en,
            'file_no': file_no,
            'age': str(age) if age else '',
            'employer_ar': employer_ar,
            'employer_en': employer_en,
            'nationality_ar': nationality_ar,
            'nationality_en': nationality_en,
            'clinic_date_hijri': clinic_date_hijri,
            'clinic_date_greg': clinic_date.strftime("%Y-%m-%d"),
            'admission_date_hijri': clinic_date_hijri,
            'admission_date_greg': clinic_date.strftime("%Y-%m-%d"),
            'discharge_date_hijri': discharge_date_hijri,
            'discharge_date_greg': discharge_date.strftime("%Y-%m-%d"),
            'leave_days': str(leave_days),
            'from_date_hijri': clinic_date_hijri,
            'to_date_hijri': discharge_date_hijri,
            'from_date_greg': clinic_date.strftime("%Y-%m-%d"),
            'to_date_greg': discharge_date.strftime("%Y-%m-%d"),
            'male_checkbox': 'Yes' if gender == 'ذكر' else 'Off',
            'female_checkbox': 'Yes' if gender == 'أنثى' else 'Off',
        }

        # اختيار القالب
        template_path = template['male_path'] if gender == 'ذكر' else template['female_path']
        if not os.path.exists(template_path):
            await message.answer("❌ ملف القالب غير موجود على السيرفر.")
            await state.finish()
            return

        # تعبئة PDF
        doc = fitz.open(template_path)
        filled_count = 0
        for page in doc:
            widgets = page.widgets()
            if widgets:
                for w in widgets:
                    field_name = w.field_name
                    if field_name in template['fields_to_fill'] and field_name in fill_values:
                        w.field_value = str(fill_values[field_name])
                        w.update()
                        filled_count += 1
        if filled_count == 0:
            logging.warning(f"No fields were filled in template {template_path}")
            # قد نكمل مع تحذير فقط

        output_stream = io.BytesIO()
        doc.save(output_stream)
        doc.close()
        output_stream.seek(0)

        # خصم الرصيد
        database.update_balance(user_id, -3, "report")

        # حفظ التقرير
        database.save_report(user_id, doctor_id, name_ar, gender)

        # إرسال الملف
        await bot.send_document(user_id, InputFile(output_stream, filename="تقرير_طبي.pdf"))

        # فحص الرصيد المنخفض
        balance = database.get_balance(user_id)
        if balance < 3:
            await bot.send_message(user_id, "⚠ رصيدك أوشك على الانتهاء.\nالرجاء إعادة الشحن لإصدار تقاريرك بنجاح ✅")

        await message.answer("✅ تم إنشاء التقرير بنجاح.", reply_markup=get_correct_keyboard(user_id))

    except Exception as e:
        logging.exception(f"Error during report generation: {e}")
        await message.answer("❌ حدث خطأ أثناء إنشاء التقرير. يرجى المحاولة لاحقاً.")
    finally:
        await state.finish()

# ========== لوحة المطور ==========
@dp.message_handler(lambda m: m.text == "👑 لوحة المطور")
async def admin_panel(message: types.Message):
    if str(message.from_user.id) != ADMIN_ID:
        return
    await message.answer("👑 لوحة التحكم", reply_markup=admin_keyboard())

# ========== إدارة الرصيد (كما هي مع تحسينات) ==========
# (نفس الكود السابق، مع إضافة try/except حول update_balance)

# ========== إدارة المناطق والمستشفيات والأقسام والأطباء (كما هي مع تصحيح العلاقات) ==========
# (جميع المعالجات السابقة تبقى، لكن نستخدم الدوال الجديدة get_doctor, get_department, get_hospital, get_region)

# ========== إعداد وتعديل نظام التقارير (محدث) ==========
@dp.message_handler(lambda m: m.text == "🛠 إعداد وتعديل نظام التقارير")
async def templates_management_menu(message: types.Message):
    if str(message.from_user.id) != ADMIN_ID:
        return
    await message.answer("إعداد وتعديل نظام التقارير:", reply_markup=templates_management_keyboard())

@dp.message_handler(lambda m: m.text == "📄 إدارة القوالب")
async def manage_templates_start(message: types.Message):
    if str(message.from_user.id) != ADMIN_ID:
        return
    doctors = database.get_doctors()
    if not doctors:
        await message.answer("لا يوجد أطباء مسجلين.", reply_markup=admin_keyboard())
        return
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    for doc in doctors:
        kb.add(f"👨‍⚕️ {doc[3]} (ID: {doc[0]})")
    kb.add("🔙 رجوع")
    await message.answer("اختر الطبيب الذي تريد إدارة قوالبه:", reply_markup=kb)
    await ManageTemplates.choose_doctor.set()

@dp.message_handler(state=ManageTemplates.choose_doctor)
async def manage_templates_choose_doctor(message: types.Message, state: FSMContext):
    if message.text == "🔙 رجوع":
        await templates_management_menu(message)
        await state.finish()
        return
    match = re.search(r'ID: (\d+)', message.text)
    if not match:
        await message.answer("❌ لم أتمكن من تحديد الطبيب.")
        return
    doctor_id = int(match.group(1))
    doctor = database.get_doctor(doctor_id)
    if not doctor:
        await message.answer("❌ الطبيب غير موجود.")
        return
    await state.update_data(doctor_id=doctor_id, doctor_name=doctor[3])
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("رفع قالب ذكر", "رفع قالب أنثى")
    kb.add("🔙 رجوع")
    await message.answer(f"الطبيب: {doctor[3]}\nاختر نوع القالب لرفعه:", reply_markup=kb)
    await ManageTemplates.upload_male.set()

@dp.message_handler(state=ManageTemplates.upload_male)
async def manage_templates_upload_male(message: types.Message, state: FSMContext):
    if message.text == "🔙 رجوع":
        await templates_management_menu(message)
        await state.finish()
        return
    if message.text == "رفع قالب ذكر":
        await message.answer("الرجاء رفع ملف PDF (قالب الذكور):", reply_markup=cancel_keyboard())
    else:
        await message.answer("❌ اختر أحد الخيارات.")

@dp.message_handler(content_types=['document'], state=ManageTemplates.upload_male)
async def handle_male_template(message: types.Message, state: FSMContext):
    if message.document:
        # فحص الملف
        file_info = await bot.get_file(message.document.file_id)
        downloaded = await bot.download_file(file_info.file_path)
        try:
            doc = fitz.open(stream=downloaded.getvalue(), filetype="pdf")
            has_fields = False
            field_types = set()
            for page in doc:
                widgets = page.widgets()
                if widgets:
                    has_fields = True
                    for w in widgets:
                        if w.field_type:  # 7 = text, 2 = checkbox, إلخ
                            field_types.add(w.field_type)
                    break
            doc.close()
            if not has_fields:
                await message.answer("❌ الملف ليس PDF Form قابلاً للتعبئة. يرجى رفع ملف يحتوي على حقول.")
                return
        except Exception as e:
            await message.answer(f"❌ خطأ في فحص الملف: {e}")
            return

        data = await state.get_data()
        doctor_id = data['doctor_id']
        doctor = database.get_doctor(doctor_id)
        department = database.get_department(doctor[1])  # doctor[1] = department_id
        hospital = database.get_hospital(department[1])  # department[1] = hospital_id
        region = database.get_region(hospital[1])        # hospital[1] = region_id

        region_code = region[1][:3].lower()
        hospital_code = hospital[2][:3].lower()
        dept_code = department[2][:3].lower()
        folder = os.path.join(TEMPLATES_DIR, region_code, hospital_code, dept_code)
        os.makedirs(folder, exist_ok=True)

        filename = f"{region_code}_{hospital_code}_{dept_code}_male.pdf"
        filepath = os.path.join(folder, filename)
        with open(filepath, "wb") as f:
            f.write(downloaded.getvalue())

        await state.update_data(male_path=filepath)
        await message.answer("✅ تم رفع قالب الذكور. الآن اختر 'رفع قالب أنثى' أو أكمل لاحقاً.")
        kb = ReplyKeyboardMarkup(resize_keyboard=True)
        kb.add("رفع قالب أنثى", "إنهاء وانتقاء الحقول")
        kb.add("🔙 رجوع")
        await message.answer("اختر الإجراء التالي:", reply_markup=kb)
        await ManageTemplates.upload_female.set()
    else:
        await message.answer("❌ يرجى رفع ملف PDF.")

@dp.message_handler(state=ManageTemplates.upload_female)
async def manage_templates_upload_female(message: types.Message, state: FSMContext):
    if message.text == "🔙 رجوع":
        await templates_management_menu(message)
        await state.finish()
        return
    if message.text == "رفع قالب أنثى":
        await message.answer("الرجاء رفع ملف PDF (قالب الإناث):", reply_markup=cancel_keyboard())
    elif message.text == "إنهاء وانتقاء الحقول":
        await ask_fields_selection(message, state)
    else:
        await message.answer("❌ اختر أحد الخيارات.")

@dp.message_handler(content_types=['document'], state=ManageTemplates.upload_female)
async def handle_female_template(message: types.Message, state: FSMContext):
    if message.document:
        # فحص الملف
        file_info = await bot.get_file(message.document.file_id)
        downloaded = await bot.download_file(file_info.file_path)
        try:
            doc = fitz.open(stream=downloaded.getvalue(), filetype="pdf")
            has_fields = False
            for page in doc:
                if page.widgets():
                    has_fields = True
                    break
            doc.close()
            if not has_fields:
                await message.answer("❌ الملف ليس PDF Form قابلاً للتعبئة.")
                return
        except Exception as e:
            await message.answer(f"❌ خطأ في فحص الملف: {e}")
            return

        data = await state.get_data()
        doctor_id = data['doctor_id']
        doctor = database.get_doctor(doctor_id)
        department = database.get_department(doctor[1])
        hospital = database.get_hospital(department[1])
        region = database.get_region(hospital[1])

        region_code = region[1][:3].lower()
        hospital_code = hospital[2][:3].lower()
        dept_code = department[2][:3].lower()
        folder = os.path.join(TEMPLATES_DIR, region_code, hospital_code, dept_code)
        os.makedirs(folder, exist_ok=True)

        filename = f"{region_code}_{hospital_code}_{dept_code}_female.pdf"
        filepath = os.path.join(folder, filename)
        with open(filepath, "wb") as f:
            f.write(downloaded.getvalue())

        await state.update_data(female_path=filepath)
        await message.answer("✅ تم رفع قالب الإناث.")
        await ask_fields_selection(message, state)
    else:
        await message.answer("❌ يرجى رفع ملف PDF.")

async def ask_fields_selection(message: types.Message, state: FSMContext):
    data = await state.get_data()
    male_path = data.get('male_path')
    female_path = data.get('female_path')

    if not male_path or not female_path:
        await message.answer("❌ يجب رفع كلا القالبين أولاً.")
        return

    # قراءة الحقول من أحد القالبين
    all_fields = set()
    for path in [male_path, female_path]:
        doc = fitz.open(path)
        for page in doc:
            widgets = page.widgets()
            if widgets:
                for w in widgets:
                    if w.field_name:
                        all_fields.add(w.field_name)
        doc.close()

    if not all_fields:
        await message.answer("⚠️ لم يتم العثور على أي حقول في القوالب. تأكد من أنها PDF Form.")
        await state.finish()
        return

    fields_list = sorted(list(all_fields))
    await state.update_data(all_fields=fields_list)

    await message.answer("أرسل قائمة بأسماء الحقول التي سيقوم البوت بتعبئتها تلقائياً، مفصولة بفواصل (مثال: full_name_ar, file_no, age):", reply_markup=back_keyboard())
    await ManageTemplates.select_fields_to_fill.set()

@dp.message_handler(state=ManageTemplates.select_fields_to_fill)
async def select_fields_to_fill(message: types.Message, state: FSMContext):
    if message.text == "🔙 رجوع":
        await templates_management_menu(message)
        await state.finish()
        return
    field_names = [f.strip() for f in message.text.split(',') if f.strip()]
    data = await state.get_data()
    all_fields = data['all_fields']
    valid_fields = [f for f in field_names if f in all_fields]
    if not valid_fields:
        await message.answer("❌ لم يتم إدخال أي حقل صحيح. حاول مرة أخرى.")
        return
    await state.update_data(fields_to_fill=valid_fields)
    await message.answer("الآن أرسل قائمة الحقول التي تريد أن يطلبها النظام من المستخدم، مفصولة بفواصل:")
    await ManageTemplates.select_user_fields.set()

@dp.message_handler(state=ManageTemplates.select_user_fields)
async def select_user_fields(message: types.Message, state: FSMContext):
    if message.text == "🔙 رجوع":
        await templates_management_menu(message)
        await state.finish()
        return
    user_fields = [f.strip() for f in message.text.split(',') if f.strip()]
    data = await state.get_data()
    all_fields = data['all_fields']
    valid_user_fields = [f for f in user_fields if f in all_fields]
    if not valid_user_fields:
        await message.answer("❌ لم يتم إدخال أي حقل صحيح. حاول مرة أخرى.")
        return

    male_path = data['male_path']
    female_path = data['female_path']
    doctor_id = data['doctor_id']
    fields_to_fill = data['fields_to_fill']
    database.save_template_config(doctor_id, male_path, female_path, fields_to_fill, valid_user_fields)

    await message.answer("✅ تم حفظ تكوين القالب بنجاح.", reply_markup=admin_keyboard())
    await state.finish()

# ========== باقي معالجات لوحة المطور الأخرى (إدارة الرصيد، إلخ) ==========
# (نفس الكود السابق مع تحسينات try/catch)

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
