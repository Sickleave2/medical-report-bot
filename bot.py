# bot.py (نسخة مستقرة مع إصلاحات الأخطاء)
import logging
import os
import io
import re
import random
import traceback
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

# إعداد logging مفصل
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = str(os.getenv("ADMIN_ID")).strip()

if not BOT_TOKEN:
    logger.error("BOT_TOKEN is not set")
    exit(1)

bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)

TEMPLATES_DIR = "templates"
os.makedirs(TEMPLATES_DIR, exist_ok=True)

# تهيئة قاعدة البيانات
try:
    database.init_db()
    database.seed_regions()
    logger.info("Database initialized successfully")
except Exception as e:
    logger.critical(f"Failed to initialize database: {e}")
    exit(1)

# ========== دوال مساعدة ==========
def slugify(text):
    if not text:
        return "noname"
    text = unidecode(text).lower()
    text = re.sub(r'\s+', '_', text)
    text = re.sub(r'[^a-z0-9_]', '', text)
    return text[:10]

def get_template_path(region_name, hospital_name, department_name, gender):
    region_code = slugify(region_name)[:3]
    hospital_code = slugify(hospital_name)[:3]
    dept_code = slugify(department_name)[:3]
    filename = f"{region_code}_{hospital_code}_{dept_code}_{gender}.pdf"
    folder = os.path.join(TEMPLATES_DIR, f"{region_code}_{hospital_code}_{dept_code}")
    os.makedirs(folder, exist_ok=True)
    return os.path.join(folder, filename)

def extract_form_fields(pdf_path):
    try:
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
    except Exception as e:
        logger.error(f"extract_form_fields error: {e}")
        return []

def fill_pdf_form(template_path, output_stream, data):
    try:
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
    except Exception as e:
        logger.error(f"fill_pdf_form error: {e}")
        raise

def generate_file_no(start_date):
    if isinstance(start_date, str):
        start_date = datetime.strptime(start_date, "%Y-%m-%d").date()
    yymmdd = start_date.strftime("%y%m%d")
    random_part = f"{random.randint(100, 999)}"
    return yymmdd + random_part

def calculate_age(birth_date):
    today = date.today()
    age = today.year - birth_date.year - ((today.month, today.day) < (birth_date.month, birth_date.day))
    return age

def gregorian_to_hijri(date_obj):
    try:
        h = Gregorian.fromdate(date_obj).to_hijri()
        return f"{h.year}-{h.month:02d}-{h.day:02d}"
    except:
        return ""

def translate_arabic_to_english(text):
    return unidecode(text) if text else ""

def validate_date(date_text):
    try:
        datetime.strptime(date_text, "%Y-%m-%d")
        return True
    except ValueError:
        return False

def doctor_has_templates(doctor_id):
    doctor = database.get_doctor(doctor_id)
    return doctor and doctor[4] and doctor[5]  # pdf_male and pdf_female

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
    kb.add("📢 الإشعارات", "🔙 رجوع")
    # الميزات الجديدة معطلة مؤقتاً حتى الاستقرار
    # kb.add("🛠 إعداد وتعديل نظام التقارير")
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

def get_correct_keyboard(user_id):
    is_admin = str(user_id) == ADMIN_ID
    return admin_keyboard() if is_admin else main_keyboard(False)

# ========== حالات FSM ==========
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

# ========== معالج الأخطاء العام ==========
@dp.errors_handler()
async def errors_handler(update, exception):
    logger.error(f"Update {update} caused error {exception}")
    try:
        if update.message:
            await update.message.answer("❌ حدث خطأ داخلي. تم إبلاغ المطور.")
        elif update.callback_query:
            await update.callback_query.message.answer("❌ حدث خطأ داخلي. تم إبلاغ المطور.")
    except:
        pass
    return True

# ========== معالج الإلغاء ==========
@dp.message_handler(lambda m: m.text == "❌ إلغاء العملية", state="*")
async def cancel_operation(message: types.Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state is None:
        await message.answer("لا توجد عملية لإلغائها.")
        return
    await state.finish()
    await message.answer("✅ تم إلغاء العملية.", reply_markup=get_correct_keyboard(message.from_user.id))

# ========== البداية ==========
@dp.message_handler(commands=['start'])
async def start(message: types.Message):
    try:
        user_id = message.from_user.id
        username = message.from_user.username or "NoUsername"
        is_admin = 1 if str(user_id) == ADMIN_ID else 0
        database.add_user(user_id, username, is_admin)
        await message.answer("🩺 أهلاً بك في نظام التقارير الطبية", reply_markup=main_keyboard(is_admin))
    except Exception as e:
        logger.error(f"start error: {e}")
        await message.answer("❌ حدث خطأ. حاول مرة أخرى لاحقاً.")

@dp.message_handler(lambda m: m.text == "ℹ️ الدعم")
async def support(message: types.Message):
    await message.answer("للتواصل مع الدعم: @SupportHandle", reply_markup=get_correct_keyboard(message.from_user.id))

@dp.message_handler(lambda m: m.text == "💰 رصيدي")
async def balance_handler(message: types.Message):
    try:
        user = database.get_user(message.from_user.id)
        if user and user[5] == 1:
            await message.answer("🚫 حسابك محظور.")
            return
        balance = database.get_balance(message.from_user.id)
        await message.answer(f"رصيدك الحالي: {balance} ريال", reply_markup=get_correct_keyboard(message.from_user.id))
    except Exception as e:
        logger.error(f"balance_handler error: {e}")
        await message.answer("❌ حدث خطأ.")

# ========== إصدار تقرير (نسخة مستقرة بدون الديناميكية الجديدة) ==========
@dp.message_handler(lambda m: m.text == "🤍 إصدار إجازتك الآن")
async def start_report(message: types.Message):
    try:
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
    except Exception as e:
        logger.error(f"start_report error: {e}")
        await message.answer("❌ حدث خطأ. حاول مرة أخرى.")

@dp.message_handler(state=CreateReport.choose_region)
async def choose_region(message: types.Message, state: FSMContext):
    try:
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
    except Exception as e:
        logger.error(f"choose_region error: {e}")
        await state.finish()
        await message.answer("❌ حدث خطأ. أعد المحاولة من البداية.", reply_markup=get_correct_keyboard(message.from_user.id))

@dp.message_handler(state=CreateReport.choose_hospital)
async def choose_hospital(message: types.Message, state: FSMContext):
    try:
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
    except Exception as e:
        logger.error(f"choose_hospital error: {e}")
        await state.finish()
        await message.answer("❌ حدث خطأ. أعد المحاولة.", reply_markup=get_correct_keyboard(message.from_user.id))

@dp.message_handler(state=CreateReport.choose_department)
async def choose_department(message: types.Message, state: FSMContext):
    try:
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
    except Exception as e:
        logger.error(f"choose_department error: {e}")
        await state.finish()
        await message.answer("❌ حدث خطأ.", reply_markup=get_correct_keyboard(message.from_user.id))

@dp.message_handler(state=CreateReport.choose_doctor)
async def choose_doctor(message: types.Message, state: FSMContext):
    try:
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

        doctor = database.get_doctor(doctor_id)
        if not doctor:
            await message.answer("❌ خطأ في بيانات الطبيب.")
            return

        # التحقق من وجود قوالب (إذا لم توجد، نكمل بدونها مؤقتاً)
        pdf_male = doctor[4] if doctor[4] else ""
        pdf_female = doctor[5] if doctor[5] else ""

        await state.update_data(doctor_id=doctor_id, doctor_name=doctor_name,
                                pdf_male=pdf_male, pdf_female=pdf_female)

        kb = ReplyKeyboardMarkup(resize_keyboard=True)
        kb.add("👨 ذكر", "👩 أنثى")
        kb.add("🔙 رجوع")
        await message.answer("اختر جنس المريض:", reply_markup=kb)
        await CreateReport.choose_gender.set()
    except Exception as e:
        logger.error(f"choose_doctor error: {e}")
        await state.finish()
        await message.answer("❌ حدث خطأ.", reply_markup=get_correct_keyboard(message.from_user.id))

@dp.message_handler(state=CreateReport.choose_gender)
async def choose_gender(message: types.Message, state: FSMContext):
    try:
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
        await state.update_data(gender=gender)

        await message.answer("أدخل اسم المريض الكامل (بالعربية):", reply_markup=cancel_keyboard())
        await CreateReport.patient_name_ar.set()
    except Exception as e:
        logger.error(f"choose_gender error: {e}")
        await state.finish()
        await message.answer("❌ حدث خطأ.", reply_markup=get_correct_keyboard(message.from_user.id))

@dp.message_handler(state=CreateReport.patient_name_ar)
async def enter_patient_name_ar(message: types.Message, state: FSMContext):
    if message.text == "❌ إلغاء العملية":
        await cancel_operation(message, state)
        return
    await state.update_data(patient_name_ar=message.text)
    await message.answer("أدخل اسم المريض الكامل (بالإنجليزية):", reply_markup=cancel_keyboard())
    await CreateReport.patient_name_en.set()

@dp.message_handler(state=CreateReport.patient_name_en)
async def enter_patient_name_en(message: types.Message, state: FSMContext):
    if message.text == "❌ إلغاء العملية":
        await cancel_operation(message, state)
        return
    await state.update_data(patient_name_en=message.text)
    await message.answer("أدخل تاريخ الميلاد (YYYY-MM-DD):", reply_markup=cancel_keyboard())
    await CreateReport.birth_date.set()

@dp.message_handler(state=CreateReport.birth_date)
async def enter_birth_date(message: types.Message, state: FSMContext):
    if message.text == "❌ إلغاء العملية":
        await cancel_operation(message, state)
        return
    try:
        birth_date = datetime.strptime(message.text, "%Y-%m-%d").date()
    except ValueError:
        await message.answer("❌ صيغة تاريخ غير صحيحة. استخدم YYYY-MM-DD")
        return
    await state.update_data(birth_date=birth_date)
    await message.answer("أدخل جهة العمل:", reply_markup=cancel_keyboard())
    await CreateReport.employer.set()

@dp.message_handler(state=CreateReport.employer)
async def enter_employer(message: types.Message, state: FSMContext):
    if message.text == "❌ إلغاء العملية":
        await cancel_operation(message, state)
        return
    await state.update_data(employer=message.text)
    await message.answer("أدخل تاريخ بداية الإجازة (YYYY-MM-DD):", reply_markup=cancel_keyboard())
    await CreateReport.start_date.set()

@dp.message_handler(state=CreateReport.start_date)
async def enter_start_date(message: types.Message, state: FSMContext):
    if message.text == "❌ إلغاء العملية":
        await cancel_operation(message, state)
        return
    try:
        start_date = datetime.strptime(message.text, "%Y-%m-%d").date()
    except ValueError:
        await message.answer("❌ صيغة تاريخ غير صحيحة. استخدم YYYY-MM-DD")
        return
    await state.update_data(start_date=start_date)
    await message.answer("أدخل عدد أيام الإجازة:", reply_markup=cancel_keyboard())
    await CreateReport.leave_days.set()

@dp.message_handler(state=CreateReport.leave_days)
async def enter_leave_days(message: types.Message, state: FSMContext):
    if message.text == "❌ إلغاء العملية":
        await cancel_operation(message, state)
        return
    if not message.text.isdigit() or int(message.text) <= 0:
        await message.answer("❌ الرجاء إدخال رقم صحيح أكبر من 0")
        return
    leave_days = int(message.text)
    data = await state.get_data()
    start_date = data["start_date"]
    end_date = start_date + timedelta(days=leave_days - 1)
    age = calculate_age(data["birth_date"])
    file_no = generate_file_no(start_date)

    clinic_date_ar = gregorian_to_hijri(start_date)
    clinic_date_en = start_date.strftime("%d-%m-%Y")
    admission_date_ar = clinic_date_ar
    admission_date_en = clinic_date_en
    discharge_date_ar = gregorian_to_hijri(end_date)
    discharge_date_en = end_date.strftime("%d-%m-%Y")
    start_date_ar = clinic_date_ar
    start_date_en = clinic_date_en
    end_date_ar = discharge_date_ar
    end_date_en = discharge_date_en

    await state.update_data(
        leave_days=leave_days,
        end_date=end_date,
        age=age,
        file_no=file_no,
        clinic_date_ar=clinic_date_ar,
        clinic_date_en=clinic_date_en,
        admission_date_ar=admission_date_ar,
        admission_date_en=admission_date_en,
        discharge_date_ar=discharge_date_ar,
        discharge_date_en=discharge_date_en,
        start_date_ar=start_date_ar,
        start_date_en=start_date_en,
        end_date_ar=end_date_ar,
        end_date_en=end_date_en
    )

    summary = (
        f"📋 ملخص البيانات:\n"
        f"👤 الاسم عربي: {data['patient_name_ar']}\n"
        f"👤 اسم إنجليزي: {data['patient_name_en']}\n"
        f"🆔 رقم الملف: {file_no}\n"
        f"🎂 العمر: {age}\n"
        f"🏢 جهة العمل: {data['employer']}\n"
        f"📅 تاريخ الميلاد: {data['birth_date']}\n"
        f"📅 بداية الإجازة: {start_date}\n"
        f"📆 عدد الأيام: {leave_days}\n"
        f"📅 نهاية الإجازة: {end_date}\n"
        f"🏥 المستشفى: {data['hospital_name']}\n"
        f"👨‍⚕️ الطبيب: {data['doctor_name']}\n"
        f"⚥ الجنس: {data['gender']}\n\n"
        f"هل البيانات صحيحة؟"
    )
    kb = yes_no_keyboard()
    kb.add("❌ إلغاء العملية")
    await message.answer(summary, reply_markup=kb)
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

    # خصم الرصيد
    try:
        database.update_balance(user_id, -3, "report")
    except Exception as e:
        logger.error(f"Error deducting balance: {e}")
        await message.answer("❌ حدث خطأ أثناء خصم الرصيد.")
        await state.finish()
        return

    # حفظ التقرير
    try:
        database.save_report(user_id, data["doctor_id"], data["patient_name_ar"], data["gender"])
    except Exception as e:
        logger.error(f"Error saving report: {e}")
        # استمر رغم الخطأ

    # اختيار القالب المناسب (إذا وجد)
    pdf_path = data["pdf_male"] if data["gender"] == "ذكر" else data["pdf_female"]

    # تجهيز بيانات التعبئة
    fill_data = {
        "full_name_ar": data["patient_name_ar"],
        "full_name_en": data["patient_name_en"],
        "file_no": data["file_no"],
        "age": str(data["age"]),
        "employer": data["employer"],
        "clinic_date_ar": data["clinic_date_ar"],
        "clinic_date_en": data["clinic_date_en"],
        "admission_date_ar": data["admission_date_ar"],
        "admission_date_en": data["admission_date_en"],
        "discharge_date_ar": data["discharge_date_ar"],
        "discharge_date_en": data["discharge_date_en"],
        "leave_days": str(data["leave_days"]),
        "start_date_ar": data["start_date_ar"],
        "start_date_en": data["start_date_en"],
        "end_date_ar": data["end_date_ar"],
        "end_date_en": data["end_date_en"]
    }

    # تعبئة وإرسال PDF
    output_stream = io.BytesIO()
    try:
        if pdf_path and os.path.exists(pdf_path):
            fill_pdf_form(pdf_path, output_stream, fill_data)
        else:
            # إذا لم يوجد قالب، ننشئ ملف نصي بسيط
            output_stream.write(b"Template not available. Here is your data:\n")
            for k, v in fill_data.items():
                output_stream.write(f"{k}: {v}\n".encode())
        output_stream.seek(0)
        await bot.send_document(user_id, InputFile(output_stream, filename="تقرير_طبي.pdf"))
    except Exception as e:
        logger.error(f"PDF generation error: {e}")
        await message.answer("❌ حدث خطأ أثناء إنشاء ملف التقرير.")
        await state.finish()
        return

    # فحص الرصيد المنخفض
    await check_low_balance(user_id)

    await message.answer("✅ تم إنشاء التقرير بنجاح.", reply_markup=get_correct_keyboard(user_id))
    await state.finish()

async def check_low_balance(user_id):
    try:
        balance = database.get_balance(user_id)
        if balance < 3:
            await bot.send_message(user_id, "⚠ رصيدك أوشك على الانتهاء.\nالرجاء إعادة الشحن لإصدار تقاريرك بنجاح ✅")
    except:
        pass

# ========== لوحة المطور ==========
@dp.message_handler(lambda m: m.text == "👑 لوحة المطور")
async def admin_panel(message: types.Message):
    if str(message.from_user.id) != ADMIN_ID:
        return
    await message.answer("👑 لوحة التحكم", reply_markup=admin_keyboard())

# ========== إدارة الرصيد ==========
@dp.message_handler(lambda m: m.text == "💰 إدارة الرصيد")
async def balance_management(message: types.Message):
    if str(message.from_user.id) != ADMIN_ID:
        return
    await message.answer("إدارة الرصيد:", reply_markup=balance_management_keyboard())

# إضافة رصيد
@dp.message_handler(lambda m: m.text == "➕ إضافة رصيد")
async def add_balance_start(message: types.Message):
    if str(message.from_user.id) != ADMIN_ID:
        return
    await message.answer("أرسل آيدي المستخدم:", reply_markup=cancel_keyboard())
    await AddBalance.user_id.set()

@dp.message_handler(state=AddBalance.user_id)
async def add_balance_user(message: types.Message, state: FSMContext):
    if message.text == "❌ إلغاء العملية":
        await cancel_operation(message, state)
        return
    if not message.text.isdigit():
        await message.answer("❌ آيدي غير صحيح.")
        return
    await state.update_data(user_id=int(message.text))
    await message.answer("أرسل المبلغ:", reply_markup=cancel_keyboard())
    await AddBalance.amount.set()

@dp.message_handler(state=AddBalance.amount)
async def add_balance_amount(message: types.Message, state: FSMContext):
    if message.text == "❌ إلغاء العملية":
        await cancel_operation(message, state)
        return
    try:
        amount = float(message.text)
        if amount <= 0 or amount > 10000:
            raise ValueError
    except:
        await message.answer("❌ مبلغ غير صحيح (1 - 10000)")
        return
    await state.update_data(amount=amount)
    await message.answer("هل تريد إرسال إشعار للمستخدم؟", reply_markup=yes_no_keyboard())
    await AddBalance.confirm_notify.set()

@dp.message_handler(state=AddBalance.confirm_notify)
async def add_balance_confirm(message: types.Message, state: FSMContext):
    if message.text == "❌ إلغاء العملية":
        await cancel_operation(message, state)
        return
    data = await state.get_data()
    user_id = data["user_id"]
    amount = data["amount"]
    try:
        database.update_balance(user_id, amount, "add")
        if message.text == "✅ نعم":
            await bot.send_message(user_id, f"💰 تم إضافة {amount} ريال إلى حسابك.\nرصيدك الحالي: {database.get_balance(user_id)} ريال")
    except Exception as e:
        logger.error(f"add_balance error: {e}")
        await message.answer("❌ حدث خطأ أثناء تنفيذ العملية.")
        await state.finish()
        return
    await message.answer("✅ تم تنفيذ العملية.", reply_markup=balance_management_keyboard())
    await state.finish()

# خصم رصيد (مشابه للإضافة مع تغيير الإشارة)
@dp.message_handler(lambda m: m.text == "➖ خصم رصيد")
async def deduct_balance_start(message: types.Message):
    if str(message.from_user.id) != ADMIN_ID:
        return
    await message.answer("أرسل آيدي المستخدم:", reply_markup=cancel_keyboard())
    await DeductBalance.user_id.set()

@dp.message_handler(state=DeductBalance.user_id)
async def deduct_balance_user(message: types.Message, state: FSMContext):
    if message.text == "❌ إلغاء العملية":
        await cancel_operation(message, state)
        return
    if not message.text.isdigit():
        await message.answer("❌ آيدي غير صحيح.")
        return
    await state.update_data(user_id=int(message.text))
    await message.answer("أرسل المبلغ:", reply_markup=cancel_keyboard())
    await DeductBalance.amount.set()

@dp.message_handler(state=DeductBalance.amount)
async def deduct_balance_amount(message: types.Message, state: FSMContext):
    if message.text == "❌ إلغاء العملية":
        await cancel_operation(message, state)
        return
    try:
        amount = float(message.text)
        if amount <= 0 or amount > 10000:
            raise ValueError
    except:
        await message.answer("❌ مبلغ غير صحيح.")
        return
    await state.update_data(amount=amount)
    await message.answer("هل تريد إرسال إشعار للمستخدم؟", reply_markup=yes_no_keyboard())
    await DeductBalance.confirm_notify.set()

@dp.message_handler(state=DeductBalance.confirm_notify)
async def deduct_balance_confirm(message: types.Message, state: FSMContext):
    if message.text == "❌ إلغاء العملية":
        await cancel_operation(message, state)
        return
    data = await state.get_data()
    user_id = data["user_id"]
    amount = data["amount"]
    try:
        database.update_balance(user_id, -amount, "deduct")
        if message.text == "✅ نعم":
            await bot.send_message(user_id, f"⚠ تم خصم {amount} ريال من حسابك.\nرصيدك الحالي: {database.get_balance(user_id)} ريال")
    except Exception as e:
        logger.error(f"deduct_balance error: {e}")
        await message.answer("❌ حدث خطأ أثناء تنفيذ العملية.")
        await state.finish()
        return
    await message.answer("✅ تم تنفيذ العملية.", reply_markup=balance_management_keyboard())
    await state.finish()

# معلومات مستخدم
@dp.message_handler(lambda m: m.text == "👤 معلومات مستخدم")
async def info_user_start(message: types.Message):
    if str(message.from_user.id) != ADMIN_ID:
        return
    await message.answer("أرسل آيدي المستخدم:", reply_markup=cancel_keyboard())
    await InfoUser.user_id.set()

@dp.message_handler(state=InfoUser.user_id)
async def info_user_execute(message: types.Message, state: FSMContext):
    if message.text == "❌ إلغاء العملية":
        await cancel_operation(message, state)
        return
    if not message.text.isdigit():
        await message.answer("❌ آيدي غير صحيح.")
        return
    user_id = int(message.text)
    user = database.get_user(user_id)
    if not user:
        await message.answer("المستخدم غير موجود.")
        await state.finish()
        return
    balance = database.get_balance(user_id)
    status = "محظور 🚫" if user[5] == 1 else "نشط ✅"
    last_tx = database.get_last_transaction(user_id)
    tx_text = "لا توجد عمليات."
    if last_tx:
        tx_text = f"{last_tx[1]} | {last_tx[0]} | {last_tx[2]}"
    await message.answer(
        f"👤 معلومات المستخدم:\n\n"
        f"🆔 ID: {user_id}\n"
        f"💰 الرصيد: {balance}\n"
        f"📌 الحالة: {status}\n"
        f"🧾 آخر عملية: {tx_text}\n"
        f"📅 تاريخ التسجيل: {user[6]}",
        reply_markup=balance_management_keyboard()
    )
    await state.finish()

# حظر
@dp.message_handler(lambda m: m.text == "🚫 حظر")
async def ban_start(message: types.Message):
    if str(message.from_user.id) != ADMIN_ID:
        return
    await message.answer("أرسل آيدي المستخدم للحظر:", reply_markup=cancel_keyboard())
    await BanUser.user_id.set()

@dp.message_handler(state=BanUser.user_id)
async def ban_execute(message: types.Message, state: FSMContext):
    if message.text == "❌ إلغاء العملية":
        await cancel_operation(message, state)
        return
    if not message.text.isdigit():
        await message.answer("❌ آيدي غير صحيح.")
        return
    user_id = int(message.text)
    database.ban_user(user_id, 1)
    try:
        await bot.send_message(user_id, "🚫 تم حظر حسابك من استخدام البوت.")
    except:
        pass
    await message.answer("🚫 تم الحظر وإرسال إشعار.", reply_markup=balance_management_keyboard())
    await state.finish()

# فك حظر
@dp.message_handler(lambda m: m.text == "🔓 فك حظر")
async def unban_start(message: types.Message):
    if str(message.from_user.id) != ADMIN_ID:
        return
    await message.answer("أرسل آيدي المستخدم لفك الحظر:", reply_markup=cancel_keyboard())
    await UnbanUser.user_id.set()

@dp.message_handler(state=UnbanUser.user_id)
async def unban_execute(message: types.Message, state: FSMContext):
    if message.text == "❌ إلغاء العملية":
        await cancel_operation(message, state)
        return
    if not message.text.isdigit():
        await message.answer("❌ آيدي غير صحيح.")
        return
    user_id = int(message.text)
    database.ban_user(user_id, 0)
    try:
        await bot.send_message(user_id, "🎉 تم فك الحظر عن حسابك.\nالآن يمكنك استخدام البوت بكامل ميزاته الخرافية 😍✔️")
    except:
        pass
    await message.answer("✅ تم فك الحظر وإرسال إشعار.", reply_markup=balance_management_keyboard())
    await state.finish()

# ========== إدارة المناطق ==========
@dp.message_handler(lambda m: m.text == "📍 إدارة المناطق")
async def manage_regions_menu(message: types.Message):
    if str(message.from_user.id) != ADMIN_ID:
        return
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("📍 عرض المناطق", "➕ إضافة منطقة", "🗑 حذف منطقة")
    kb.add("🔙 رجوع")
    await message.answer("إدارة المناطق:", reply_markup=kb)

@dp.message_handler(lambda m: m.text == "📍 عرض المناطق")
async def list_regions(message: types.Message):
    if str(message.from_user.id) != ADMIN_ID:
        return
    try:
        regions = database.get_regions()
        if not regions:
            await message.answer("لا توجد مناطق مسجلة.", reply_markup=admin_keyboard())
            return
        text = "المناطق المسجلة:\n\n"
        for r in regions:
            text += f"🆔 {r[0]} | {r[1]}\n"
        await message.answer(text, reply_markup=admin_keyboard())
    except Exception as e:
        logger.error(f"list_regions error: {e}")
        await message.answer("❌ حدث خطأ.", reply_markup=admin_keyboard())

@dp.message_handler(lambda m: m.text == "➕ إضافة منطقة")
async def add_region_start(message: types.Message):
    if str(message.from_user.id) != ADMIN_ID:
        return
    await message.answer("أرسل اسم المنطقة الجديدة:", reply_markup=cancel_keyboard())
    await AddRegion.name.set()

@dp.message_handler(state=AddRegion.name)
async def add_region_name(message: types.Message, state: FSMContext):
    if message.text == "❌ إلغاء العملية":
        await cancel_operation(message, state)
        return
    name = message.text.strip()
    if name:
        try:
            database.add_region(name)
            await message.answer(f"✅ تم إضافة المنطقة '{name}'", reply_markup=admin_keyboard())
        except Exception as e:
            logger.error(f"add_region error: {e}")
            await message.answer("❌ حدث خطأ أثناء الإضافة.")
    else:
        await message.answer("❌ اسم غير صالح.")
    await state.finish()

@dp.message_handler(lambda m: m.text == "🗑 حذف منطقة")
async def delete_region_start(message: types.Message):
    if str(message.from_user.id) != ADMIN_ID:
        return
    regions = database.get_regions()
    if not regions:
        await message.answer("لا توجد مناطق مسجلة.", reply_markup=admin_keyboard())
        return
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    for r in regions:
        kb.add(f"🗑 {r[1]}")
    kb.add("🔙 رجوع")
    await message.answer("اختر المنطقة للحذف:", reply_markup=kb)
    await DeleteRegion.choose.set()

@dp.message_handler(state=DeleteRegion.choose)
async def delete_region_execute(message: types.Message, state: FSMContext):
    if message.text == "🔙 رجوع":
        await manage_regions_menu(message)
        await state.finish()
        return
    region_name = message.text.replace("🗑 ", "")
    regions = database.get_regions()
    region_id = None
    for r in regions:
        if r[1] == region_name:
            region_id = r[0]
            break
    if region_id:
        try:
            database.delete_region(region_id)
            await message.answer(f"✅ تم حذف المنطقة '{region_name}'", reply_markup=admin_keyboard())
        except Exception as e:
            logger.error(f"delete_region error: {e}")
            await message.answer("❌ حدث خطأ أثناء الحذف.")
    else:
        await message.answer("❌ المنطقة غير موجودة.")
    await state.finish()

# ========== إدارة المستشفيات ==========
@dp.message_handler(lambda m: m.text == "🏥 إدارة المستشفيات")
async def manage_hospitals_menu(message: types.Message):
    if str(message.from_user.id) != ADMIN_ID:
        return
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("🏥 عرض المستشفيات", "➕ إضافة مستشفى", "🗑 حذف مستشفى")
    kb.add("🔙 رجوع")
    await message.answer("إدارة المستشفيات:", reply_markup=kb)

@dp.message_handler(lambda m: m.text == "🏥 عرض المستشفيات")
async def list_hospitals(message: types.Message):
    if str(message.from_user.id) != ADMIN_ID:
        return
    try:
        hospitals = database.get_hospitals()
        if not hospitals:
            await message.answer("لا توجد مستشفيات مسجلة.", reply_markup=admin_keyboard())
            return
        text = "المستشفيات المسجلة:\n\n"
        for h in hospitals:
            text += f"🆔 {h[0]} | {h[2]}\n"
        await message.answer(text, reply_markup=admin_keyboard())
    except Exception as e:
        logger.error(f"list_hospitals error: {e}")
        await message.answer("❌ حدث خطأ.")

@dp.message_handler(lambda m: m.text == "➕ إضافة مستشفى")
async def add_hospital_start(message: types.Message):
    if str(message.from_user.id) != ADMIN_ID:
        return
    regions = database.get_regions()
    if not regions:
        await message.answer("يجب إضافة منطقة أولاً.", reply_markup=admin_keyboard())
        return
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    for r in regions:
        kb.add(f"📍 {r[1]}")
    kb.add("🔙 رجوع")
    await message.answer("اختر المنطقة:", reply_markup=kb)
    await AddHospital.region.set()

@dp.message_handler(state=AddHospital.region)
async def add_hospital_region(message: types.Message, state: FSMContext):
    if message.text == "🔙 رجوع":
        await manage_hospitals_menu(message)
        await state.finish()
        return
    region_name = message.text.replace("📍 ", "")
    regions = database.get_regions()
    region_id = None
    for r in regions:
        if r[1] == region_name:
            region_id = r[0]
            break
    if not region_id:
        await message.answer("❌ منطقة غير صحيحة.")
        return
    await state.update_data(region_id=region_id)
    await message.answer("أرسل اسم المستشفى:", reply_markup=cancel_keyboard())
    await AddHospital.name.set()

@dp.message_handler(state=AddHospital.name)
async def add_hospital_name(message: types.Message, state: FSMContext):
    if message.text == "❌ إلغاء العملية":
        await cancel_operation(message, state)
        return
    name = message.text.strip()
    if name:
        try:
            data = await state.get_data()
            database.add_hospital(data["region_id"], name)
            await message.answer(f"✅ تم إضافة المستشفى '{name}'", reply_markup=admin_keyboard())
        except Exception as e:
            logger.error(f"add_hospital error: {e}")
            await message.answer("❌ حدث خطأ أثناء الإضافة.")
    else:
        await message.answer("❌ اسم غير صالح.")
    await state.finish()

@dp.message_handler(lambda m: m.text == "🗑 حذف مستشفى")
async def delete_hospital_start(message: types.Message):
    if str(message.from_user.id) != ADMIN_ID:
        return
    hospitals = database.get_hospitals()
    if not hospitals:
        await message.answer("لا توجد مستشفيات مسجلة.", reply_markup=admin_keyboard())
        return
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    for h in hospitals:
        kb.add(f"🗑 {h[2]}")
    kb.add("🔙 رجوع")
    await message.answer("اختر المستشفى للحذف:", reply_markup=kb)
    await DeleteHospital.choose.set()

@dp.message_handler(state=DeleteHospital.choose)
async def delete_hospital_execute(message: types.Message, state: FSMContext):
    if message.text == "🔙 رجوع":
        await manage_hospitals_menu(message)
        await state.finish()
        return
    hospital_name = message.text.replace("🗑 ", "")
    hospitals = database.get_hospitals()
    hospital_id = None
    for h in hospitals:
        if h[2] == hospital_name:
            hospital_id = h[0]
            break
    if hospital_id:
        try:
            database.delete_hospital(hospital_id)
            await message.answer(f"✅ تم حذف المستشفى '{hospital_name}'", reply_markup=admin_keyboard())
        except Exception as e:
            logger.error(f"delete_hospital error: {e}")
            await message.answer("❌ حدث خطأ أثناء الحذف.")
    else:
        await message.answer("❌ المستشفى غير موجود.")
    await state.finish()

# ========== إدارة الأقسام ==========
@dp.message_handler(lambda m: m.text == "🩺 إدارة الأقسام")
async def manage_departments_menu(message: types.Message):
    if str(message.from_user.id) != ADMIN_ID:
        return
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("🩺 عرض الأقسام", "➕ إضافة قسم", "🗑 حذف قسم")
    kb.add("🔙 رجوع")
    await message.answer("إدارة الأقسام:", reply_markup=kb)

@dp.message_handler(lambda m: m.text == "🩺 عرض الأقسام")
async def list_departments(message: types.Message):
    if str(message.from_user.id) != ADMIN_ID:
        return
    try:
        departments = database.get_departments()
        if not departments:
            await message.answer("لا توجد أقسام مسجلة.", reply_markup=admin_keyboard())
            return
        text = "الأقسام المسجلة:\n\n"
        for d in departments:
            text += f"🆔 {d[0]} | {d[2]}\n"
        await message.answer(text, reply_markup=admin_keyboard())
    except Exception as e:
        logger.error(f"list_departments error: {e}")
        await message.answer("❌ حدث خطأ.")

@dp.message_handler(lambda m: m.text == "➕ إضافة قسم")
async def add_department_start(message: types.Message):
    if str(message.from_user.id) != ADMIN_ID:
        return
    regions = database.get_regions()
    if not regions:
        await message.answer("يجب إضافة منطقة أولاً.", reply_markup=admin_keyboard())
        return
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    for r in regions:
        kb.add(f"📍 {r[1]}")
    kb.add("🔙 رجوع")
    await message.answer("اختر المنطقة:", reply_markup=kb)
    await AddDepartment.region.set()

@dp.message_handler(state=AddDepartment.region)
async def add_department_region(message: types.Message, state: FSMContext):
    if message.text == "🔙 رجوع":
        await manage_departments_menu(message)
        await state.finish()
        return
    region_name = message.text.replace("📍 ", "")
    regions = database.get_regions()
    region_id = None
    for r in regions:
        if r[1] == region_name:
            region_id = r[0]
            break
    if not region_id:
        await message.answer("❌ منطقة غير صحيحة.")
        return
    await state.update_data(region_id=region_id)
    hospitals = database.get_hospitals(region_id)
    if not hospitals:
        await message.answer("لا توجد مستشفيات في هذه المنطقة.")
        await state.finish()
        return
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    for h in hospitals:
        kb.add(f"🏥 {h[2]}")
    kb.add("🔙 رجوع")
    await message.answer("اختر المستشفى:", reply_markup=kb)
    await AddDepartment.hospital.set()

@dp.message_handler(state=AddDepartment.hospital)
async def add_department_hospital(message: types.Message, state: FSMContext):
    if message.text == "🔙 رجوع":
        await manage_departments_menu(message)
        await state.finish()
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
        await message.answer("❌ مستشفى غير صحيح.")
        return
    await state.update_data(hospital_id=hospital_id)
    await message.answer("أرسل اسم القسم:", reply_markup=cancel_keyboard())
    await AddDepartment.name.set()

@dp.message_handler(state=AddDepartment.name)
async def add_department_name(message: types.Message, state: FSMContext):
    if message.text == "❌ إلغاء العملية":
        await cancel_operation(message, state)
        return
    name = message.text.strip()
    if name:
        try:
            data = await state.get_data()
            database.add_department(data["hospital_id"], name)
            await message.answer(f"✅ تم إضافة القسم '{name}'", reply_markup=admin_keyboard())
        except Exception as e:
            logger.error(f"add_department error: {e}")
            await message.answer("❌ حدث خطأ أثناء الإضافة.")
    else:
        await message.answer("❌ اسم غير صالح.")
    await state.finish()

@dp.message_handler(lambda m: m.text == "🗑 حذف قسم")
async def delete_department_start(message: types.Message):
    if str(message.from_user.id) != ADMIN_ID:
        return
    departments = database.get_departments()
    if not departments:
        await message.answer("لا توجد أقسام مسجلة.", reply_markup=admin_keyboard())
        return
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    for d in departments:
        kb.add(f"🗑 {d[2]}")
    kb.add("🔙 رجوع")
    await message.answer("اختر القسم للحذف:", reply_markup=kb)
    await DeleteDepartment.choose.set()

@dp.message_handler(state=DeleteDepartment.choose)
async def delete_department_execute(message: types.Message, state: FSMContext):
    if message.text == "🔙 رجوع":
        await manage_departments_menu(message)
        await state.finish()
        return
    department_name = message.text.replace("🗑 ", "")
    departments = database.get_departments()
    department_id = None
    for d in departments:
        if d[2] == department_name:
            department_id = d[0]
            break
    if department_id:
        try:
            database.delete_department(department_id)
            await message.answer(f"✅ تم حذف القسم '{department_name}'", reply_markup=admin_keyboard())
        except Exception as e:
            logger.error(f"delete_department error: {e}")
            await message.answer("❌ حدث خطأ أثناء الحذف.")
    else:
        await message.answer("❌ القسم غير موجود.")
    await state.finish()

# ========== إدارة الأطباء (بدون الميزات الجديدة) ==========
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
    try:
        doctors = database.get_doctors()
        if not doctors:
            await message.answer("لا يوجد أطباء مسجلين.", reply_markup=admin_keyboard())
            return
        text = "الأطباء المسجلون:\n\n"
        for doc in doctors:
            text += f"🆔 {doc[0]} | {doc[3]} - {doc[4]}\n"
        await message.answer(text, reply_markup=admin_keyboard())
    except Exception as e:
        logger.error(f"list_doctors error: {e}")
        await message.answer("❌ حدث خطأ.")

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
        kb.add(f"📍 {r[1]}")
    kb.add("🔙 رجوع")
    await message.answer("اختر المنطقة:", reply_markup=kb)
    await AddDoctor.region.set()

@dp.message_handler(state=AddDoctor.region)
async def add_doctor_region(message: types.Message, state: FSMContext):
    if message.text == "🔙 رجوع":
        await manage_doctors_menu(message)
        await state.finish()
        return
    region_name = message.text.replace("📍 ", "")
    regions = database.get_regions()
    region_id = None
    for r in regions:
        if r[1] == region_name:
            region_id = r[0]
            break
    if not region_id:
        await message.answer("❌ منطقة غير صحيحة.")
        return
    await state.update_data(region_id=region_id)
    hospitals = database.get_hospitals(region_id)
    if not hospitals:
        await message.answer("لا توجد مستشفيات في هذه المنطقة.")
        await state.finish()
        return
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    for h in hospitals:
        kb.add(f"🏥 {h[2]}")
    kb.add("🔙 رجوع")
    await message.answer("اختر المستشفى:", reply_markup=kb)
    await AddDoctor.hospital.set()

@dp.message_handler(state=AddDoctor.hospital)
async def add_doctor_hospital(message: types.Message, state: FSMContext):
    if message.text == "🔙 رجوع":
        await manage_doctors_menu(message)
        await state.finish()
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
        await message.answer("❌ مستشفى غير صحيح.")
        return
    await state.update_data(hospital_id=hospital_id)
    departments = database.get_departments(hospital_id)
    if not departments:
        await message.answer("لا توجد أقسام في هذا المستشفى.")
        await state.finish()
        return
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    for d in departments:
        kb.add(f"🩺 {d[2]}")
    kb.add("🔙 رجوع")
    await message.answer("اختر القسم:", reply_markup=kb)
    await AddDoctor.department.set()

@dp.message_handler(state=AddDoctor.department)
async def add_doctor_department(message: types.Message, state: FSMContext):
    if message.text == "🔙 رجوع":
        await manage_doctors_menu(message)
        await state.finish()
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
        await message.answer("❌ قسم غير صحيح.")
        return
    await state.update_data(department_id=department_id)
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

    try:
        # تحميل الملفات
        male_file_info = await bot.get_file(data["pdf_male_id"])
        male_bytes = await bot.download_file(male_file_info.file_path)
        female_file_info = await bot.get_file(file_id_female)
        female_bytes = await bot.download_file(female_file_info.file_path)

        region_name = data["region_name"] if "region_name" in data else "منطقة"
        hospital_name = data["hospital_name"] if "hospital_name" in data else "مستشفى"
        department_name = data["department_name"] if "department_name" in data else "قسم"

        male_path = get_template_path(region_name, hospital_name, department_name, "male")
        female_path = get_template_path(region_name, hospital_name, department_name, "female")

        with open(male_path, "wb") as f:
            f.write(male_bytes.getvalue())
        with open(female_path, "wb") as f:
            f.write(female_bytes.getvalue())

        # إضافة الطبيب
        doctor_id = database.add_doctor(
            data["department_id"],
            data["name"],
            data["title"],
            male_path,
            female_path
        )

        await message.answer(f"✅ تم إضافة الطبيب '{data['name']}' بنجاح.", reply_markup=admin_keyboard())
    except Exception as e:
        logger.error(f"add_doctor_pdf_female error: {e}")
        await message.answer("❌ حدث خطأ أثناء حفظ القوالب. تمت إضافة الطبيب بدون ملفات PDF.")
        # إضافة الطبيب بدون ملفات
        database.add_doctor(
            data["department_id"],
            data["name"],
            data["title"],
            "",
            ""
        )
        await message.answer(f"✅ تم إضافة الطبيب '{data['name']}' بدون قوالب.", reply_markup=admin_keyboard())

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
        kb.add(f"🗑 {doc[3]}")
    kb.add("🔙 رجوع")
    await message.answer("اختر الطبيب للحذف:", reply_markup=kb)
    await DeleteDoctor.choose.set()

@dp.message_handler(state=DeleteDoctor.choose)
async def delete_doctor_execute(message: types.Message, state: FSMContext):
    if message.text == "🔙 رجوع":
        await manage_doctors_menu(message)
        await state.finish()
        return
    doctor_name = message.text.replace("🗑 ", "")
    doctors = database.get_doctors()
    doctor_id = None
    for doc in doctors:
        if doc[3] == doctor_name:
            doctor_id = doc[0]
            break
    if doctor_id:
        try:
            database.delete_doctor(doctor_id)
            await message.answer(f"✅ تم حذف الطبيب '{doctor_name}'", reply_markup=admin_keyboard())
        except Exception as e:
            logger.error(f"delete_doctor error: {e}")
            await message.answer("❌ حدث خطأ أثناء الحذف.")
    else:
        await message.answer("❌ الطبيب غير موجود.")
    await state.finish()

# ========== الإحصائيات ==========
@dp.message_handler(lambda m: m.text == "📊 الإحصائيات")
async def stats(message: types.Message):
    if str(message.from_user.id) != ADMIN_ID:
        return
    try:
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
    except Exception as e:
        logger.error(f"stats error: {e}")
        await message.answer("❌ حدث خطأ في جلب الإحصائيات.", reply_markup=admin_keyboard())

# ========== الإشعارات ==========
@dp.message_handler(lambda m: m.text == "📢 الإشعارات")
async def notifications_menu(message: types.Message):
    if str(message.from_user.id) != ADMIN_ID:
        return
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("📢 إشعار لمستخدم", "📣 إشعار جماعي")
    kb.add("🔙 رجوع")
    await message.answer("الإشعارات:", reply_markup=kb)

@dp.message_handler(lambda m: m.text == "📢 إشعار لمستخدم")
async def notify_user_start(message: types.Message):
    if str(message.from_user.id) != ADMIN_ID:
        return
    await message.answer("أرسل آيدي المستخدم:", reply_markup=cancel_keyboard())
    await NotifyUser.user_id.set()

@dp.message_handler(state=NotifyUser.user_id)
async def notify_user_get_id(message: types.Message, state: FSMContext):
    if message.text == "❌ إلغاء العملية":
        await cancel_operation(message, state)
        return
    if not message.text.isdigit():
        await message.answer("❌ آيدي غير صحيح.")
        return
    await state.update_data(user_id=int(message.text))
    await message.answer("أرسل نص الرسالة:", reply_markup=cancel_keyboard())
    await NotifyUser.message.set()

@dp.message_handler(state=NotifyUser.message)
async def notify_user_message(message: types.Message, state: FSMContext):
    if message.text == "❌ إلغاء العملية":
        await cancel_operation(message, state)
        return
    await state.update_data(text=message.text)
    await message.answer("هل تريد إرسال الإشعار؟", reply_markup=yes_no_keyboard())
    await NotifyUser.confirm.set()

@dp.message_handler(state=NotifyUser.confirm)
async def notify_user_confirm(message: types.Message, state: FSMContext):
    if message.text == "❌ إلغاء العملية":
        await cancel_operation(message, state)
        return
    data = await state.get_data()
    if message.text == "✅ نعم":
        try:
            await bot.send_message(data["user_id"], data["text"])
            await message.answer("✅ تم إرسال الإشعار.", reply_markup=admin_keyboard())
        except Exception as e:
            logger.error(f"notify error: {e}")
            await message.answer("❌ فشل إرسال الإشعار.", reply_markup=admin_keyboard())
    else:
        await message.answer("❌ تم إلغاء الإرسال.", reply_markup=admin_keyboard())
    await state.finish()

@dp.message_handler(lambda m: m.text == "📣 إشعار جماعي")
async def broadcast_start(message: types.Message):
    if str(message.from_user.id) != ADMIN_ID:
        return
    await message.answer("أرسل نص الرسالة الجماعية:", reply_markup=cancel_keyboard())
    await Broadcast.message.set()

@dp.message_handler(state=Broadcast.message)
async def broadcast_message(message: types.Message, state: FSMContext):
    if message.text == "❌ إلغاء العملية":
        await cancel_operation(message, state)
        return
    await state.update_data(text=message.text)
    await message.answer("هل تريد إرسال الإشعار لكل المستخدمين النشطين؟", reply_markup=yes_no_keyboard())
    await Broadcast.confirm.set()

@dp.message_handler(state=Broadcast.confirm)
async def broadcast_confirm(message: types.Message, state: FSMContext):
    if message.text == "❌ إلغاء العملية":
        await cancel_operation(message, state)
        return
    if message.text == "✅ نعم":
        data = await state.get_data()
        users = database.get_all_active_users()
        count = 0
        for user_id in users:
            try:
                await bot.send_message(user_id, data["text"])
                count += 1
            except:
                pass
        await message.answer(f"✅ تم الإرسال إلى {count} مستخدم.", reply_markup=admin_keyboard())
    else:
        await message.answer("❌ تم إلغاء العملية.", reply_markup=admin_keyboard())
    await state.finish()

# ========== العودة للقائمة الرئيسية ==========
@dp.message_handler(lambda m: m.text == "🔙 رجوع", state="*")
async def back_main(message: types.Message, state: FSMContext):
    if await state.get_state() is not None:
        await state.finish()
        await message.answer("❌ تم إلغاء العملية للرجوع.")
    is_admin = str(message.from_user.id) == ADMIN_ID
    await message.answer("القائمة الرئيسية", reply_markup=main_keyboard(is_admin))

if __name__ == "__main__":
    logger.info("Starting bot...")
    executor.start_polling(dp, skip_updates=True)
