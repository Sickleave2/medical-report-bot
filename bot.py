# bot.py (النسخة النهائية مع إصلاح خطأ wait_male_config)
import logging
import os
import io
import re
import random
import traceback
from datetime import datetime, timedelta, date
from hijri_converter import Gregorian
from unidecode import unidecode
from aiogram import Bot, Dispatcher, executor, types
from aiogram.types import ReplyKeyboardMarkup, ReplyKeyboardRemove, InputFile, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.contrib.fsm_storage.memory import MemoryStorage
import database
from navigation import Navigation
from pdf_processor import SmartPDFProcessor

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = str(os.getenv("ADMIN_ID")).strip()
DEVELOPER_ID = int(ADMIN_ID)  # للمقارنة المباشرة

if not BOT_TOKEN:
    logger.error("BOT_TOKEN is not set")
    exit(1)

bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)

TEMPLATES_DIR = "templates"
os.makedirs(TEMPLATES_DIR, exist_ok=True)

database.init_db()
database.seed_regions()

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

def validate_date(date_text):
    try:
        datetime.strptime(date_text, "%Y-%m-%d")
        return True
    except ValueError:
        return False

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

# دوال التحقق من الصلاحيات
def is_developer(user_id):
    return str(user_id) == ADMIN_ID

def is_admin_user(user_id):
    # المطور دائماً Admin
    if is_developer(user_id):
        return True
    # التحقق من جدول admins
    return database.is_admin(user_id)

# ========== لوحات المفاتيح ==========
def main_keyboard(is_admin=False):
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("🤍 إصدار إجازتك الآن", "💰 رصيدي")
    kb.add("ℹ️ الدعم")
    if is_admin:
        kb.add("👑 لوحة المطور")
    return kb

def admin_keyboard(user_id):
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("💰 إدارة الرصيد", "📍 إدارة المناطق")
    kb.add("🏥 إدارة المستشفيات", "🩺 إدارة الأقسام")
    kb.add("👨‍⚕️ إدارة الأطباء", "💵 إدارة الأسعار")
    kb.add("📄 رفع قالب طبي", "📊 الإحصائيات")
    kb.add("📢 الإشعارات")
    if is_developer(user_id):
        kb.add("👥 إدارة المشرفين")
    kb.add("🔙 رجوع")
    return kb

def balance_management_keyboard():
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("➕ إضافة رصيد", "➖ خصم رصيد")
    kb.add("👤 معلومات مستخدم", "🚫 حظر", "🔓 فك حظر")
    kb.add("🔙 رجوع")
    return kb

def nav_keyboard(base_kb):
    """إضافة أزرار التنقل إلى لوحة موجودة"""
    base_kb.add("🔙 رجوع", "🏠 الرئيسية")
    return base_kb

def cancel_keyboard():
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("❌ إلغاء العملية", "🏠 الرئيسية")
    return kb

def yes_no_keyboard():
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("✅ نعم", "❌ لا")
    return kb

def get_correct_keyboard(user_id):
    if is_admin_user(user_id):
        return admin_keyboard(user_id)
    return main_keyboard(False)

# ========== دوال عرض الحالات ==========
async def show_region_selection(message: types.Message, state: FSMContext):
    regions = database.get_regions()
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    for r in regions:
        kb.add(f"📍 {r[1]}")
    kb = nav_keyboard(kb)
    await message.answer("اختر المنطقة:", reply_markup=kb)

async def show_hospital_selection(message: types.Message, state: FSMContext):
    data = await state.get_data()
    hospitals = database.get_hospitals(data["region_id"])
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    for h in hospitals:
        kb.add(f"🏥 {h[2]}")
    kb = nav_keyboard(kb)
    await message.answer("اختر المستشفى:", reply_markup=kb)

async def show_department_selection(message: types.Message, state: FSMContext):
    data = await state.get_data()
    departments = database.get_departments(data["hospital_id"])
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    for d in departments:
        kb.add(f"🩺 {d[2]}")
    kb = nav_keyboard(kb)
    await message.answer("اختر القسم:", reply_markup=kb)

async def show_doctor_selection(message: types.Message, state: FSMContext):
    data = await state.get_data()
    doctors = database.get_doctors(data["department_id"])
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    for doc in doctors:
        kb.add(f"👨‍⚕️ {doc[3]}")
    kb = nav_keyboard(kb)
    await message.answer("اختر الطبيب:", reply_markup=kb)

async def show_gender_selection(message: types.Message, state: FSMContext):
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("👨 ذكر", "👩 أنثى")
    kb = nav_keyboard(kb)
    await message.answer("اختر جنس المريض:", reply_markup=kb)

async def go_to_main(message: types.Message, state: FSMContext):
    await state.finish()
    if is_admin_user(message.from_user.id):
        await message.answer("تم العودة للقائمة الرئيسية.", reply_markup=admin_keyboard(message.from_user.id))
    else:
        await message.answer("تم العودة للقائمة الرئيسية.", reply_markup=main_keyboard(False))

# ========== دوال إنشاء لوحات الأزرار التفاعلية لاختيار الحقول ==========
def get_fields_keyboard(all_fields, selected_fields, gender_code):
    keyboard = InlineKeyboardMarkup(row_width=2)
    for field in all_fields:
        status = "✅" if field in selected_fields else "❌"
        cb_data = f"toggle_{gender_code}_{field}"
        keyboard.insert(InlineKeyboardButton(f"{status} {field}", callback_data=cb_data))
    keyboard.add(InlineKeyboardButton("💾 حفظ هذه الحقول", callback_data=f"save_{gender_code}"))
    return keyboard

# ========== حالات FSM ==========
class CreateReport(StatesGroup):
    choose_region = State()
    choose_hospital = State()
    choose_department = State()
    choose_doctor = State()
    choose_gender = State()
    patient_name = State()
    age = State()
    employer = State()
    date = State()
    days = State()
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
    title = State()   # لم نعد نحتاج pdf_male/female

class DeleteDoctor(StatesGroup):
    choose = State()

class AddAdmin(StatesGroup):
    user_id = State()
    confirm = State()

class RemoveAdmin(StatesGroup):
    choose = State()
    confirm = State()

class UploadTemplate(StatesGroup):
    choose_region = State()
    choose_hospital = State()
    choose_department = State()
    choose_doctor = State()
    choose_gender = State()
    upload_file = State()
    confirm_fields = State()

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

class PriceManagement(StatesGroup):
    choose_hospital = State()
    new_price = State()
    
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

# ========== بداية البوت ==========
@dp.message_handler(commands=['start'])
async def start(message: types.Message):
    try:
        user_id = message.from_user.id
        username = message.from_user.username or "NoUsername"
        # نحدد is_admin بناءً على وجوده في جدول المشرفين أو كونه المطور
        is_admin_flag = 1 if is_admin_user(user_id) else 0
        database.add_user(user_id, username, is_admin_flag)
        if is_admin_user(user_id):
            await message.answer("🩺 أهلاً بك في نظام التقارير الطبية (وضع المشرف)", reply_markup=admin_keyboard(user_id))
        else:
            await message.answer("🩺 أهلاً بك في نظام التقارير الطبية", reply_markup=main_keyboard(False))
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

# ========== إصدار تقرير ==========
@dp.message_handler(lambda m: m.text == "🤍 إصدار إجازتك الآن")
async def start_report(message: types.Message):
    try:
        user_id = message.from_user.id
        user = database.get_user(user_id)
        if user and user[5] == 1:
            await message.answer("🚫 حسابك محظور.")
            return

        regions = database.get_regions()
        if not regions:
            await message.answer("لا توجد مناطق مسجلة حالياً، يرجى التواصل مع المطور.")
            return

        await show_region_selection(message, None)
        await CreateReport.choose_region.set()
    except Exception as e:
        logger.error(f"start_report error: {e}")
        await message.answer("❌ حدث خطأ. حاول مرة أخرى.")

@dp.message_handler(state=CreateReport.choose_region)
async def choose_region(message: types.Message, state: FSMContext):
    if message.text == "🏠 الرئيسية":
        await go_to_main(message, state)
        return
    if message.text == "🔙 رجوع":
        await message.answer("أنت في البداية، لا يمكن الرجوع.")
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
        kb = nav_keyboard(kb)
        await message.answer("⚠️ لا توجد مستشفيات في هذه المنطقة حالياً. اختر منطقة أخرى:", reply_markup=kb)
        return

    await state.update_data(region_id=region_id)
    await show_hospital_selection(message, state)
    await CreateReport.choose_hospital.set()

@dp.message_handler(state=CreateReport.choose_hospital)
async def choose_hospital(message: types.Message, state: FSMContext):
    if message.text == "🏠 الرئيسية":
        await go_to_main(message, state)
        return
    if message.text == "🔙 رجوع":
        await state.set_state(CreateReport.choose_region)
        await show_region_selection(message, state)
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

    # التحقق من الرصيد
    price = database.get_hospital_price(hospital_id)
    user_id = message.from_user.id
    balance = database.get_balance(user_id)
    if float(balance) < price:
        await message.answer(f"❌ رصيدك غير كافي. تكلفة التقرير من هذا المستشفى {price} ريال.\nرصيدك الحالي: {balance} ريال")
        await state.finish()
        return

    departments = database.get_departments(hospital_id)
    if not departments:
        await message.answer("⚠️ لا توجد أقسام في هذا المستشفى حالياً.")
        await state.finish()
        return

    await state.update_data(hospital_id=hospital_id, hospital_name=hospital_name, price=price)
    await show_department_selection(message, state)
    await CreateReport.choose_department.set()

@dp.message_handler(state=CreateReport.choose_department)
async def choose_department(message: types.Message, state: FSMContext):
    if message.text == "🏠 الرئيسية":
        await go_to_main(message, state)
        return
    if message.text == "🔙 رجوع":
        await state.set_state(CreateReport.choose_hospital)
        await show_hospital_selection(message, state)
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
    await show_doctor_selection(message, state)
    await CreateReport.choose_doctor.set()

@dp.message_handler(state=CreateReport.choose_doctor)
async def choose_doctor(message: types.Message, state: FSMContext):
    if message.text == "🏠 الرئيسية":
        await go_to_main(message, state)
        return
    if message.text == "🔙 رجوع":
        await state.set_state(CreateReport.choose_department)
        await show_department_selection(message, state)
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
    await state.update_data(doctor_id=doctor_id, doctor_name=doctor_name,
                            pdf_male=doctor[4], pdf_female=doctor[5])

    await show_gender_selection(message, state)
    await CreateReport.choose_gender.set()

@dp.message_handler(state=CreateReport.choose_gender)
async def choose_gender(message: types.Message, state: FSMContext):
    if message.text == "🏠 الرئيسية":
        await go_to_main(message, state)
        return
    if message.text == "🔙 رجوع":
        await state.set_state(CreateReport.choose_doctor)
        await show_doctor_selection(message, state)
        return

    gender_map = {"👨 ذكر": "ذكر", "👩 أنثى": "أنثى"}
    if message.text not in gender_map:
        await message.answer("❌ اختيار غير صحيح.")
        return
    gender = gender_map[message.text]
    await state.update_data(gender=gender)

    await message.answer(
        "أرسل بياناتك بالتنسيق التالي:\n"
        "الاسم الكامل\n"
        "العمر (رقم)\n"
        "جهة العمل\n"
        "تاريخ الإجازة (YYYY-MM-DD)\n"
        "عدد الأيام\n\n"
        "مثال:\n"
        "أحمد محمد\n"
        "35\n"
        "شركة الأمل\n"
        "2026-02-04\n"
        "7",
        reply_markup=cancel_keyboard()
    )
    await CreateReport.patient_name.set()

@dp.message_handler(state=CreateReport.patient_name)
async def collect_data(message: types.Message, state: FSMContext):
    if message.text == "🏠 الرئيسية":
        await go_to_main(message, state)
        return
    if message.text == "❌ إلغاء العملية":
        await cancel_operation(message, state)
        return

    lines = message.text.strip().split('\n')
    if len(lines) < 5:
        await message.answer("❌ يجب إرسال 5 أسطر بالترتيب المطلوب. حاول مرة أخرى.")
        return

    patient_name = lines[0].strip()
    age = lines[1].strip()
    employer = lines[2].strip()
    date_str = lines[3].strip()
    days_str = lines[4].strip()

    if not patient_name or not age.isdigit() or not employer or not validate_date(date_str) or not days_str.isdigit():
        await message.answer("❌ أحد المدخلات غير صحيح. تأكد من الصيغة.")
        return

    age = int(age)
    days = int(days_str)
    date_obj = datetime.strptime(date_str, "%Y-%m-%d").date()

    await state.update_data(
        patient_name=patient_name,
        age=age,
        employer=employer,
        date=date_str,
        days=days
    )

    data = await state.get_data()
    price = data["price"]
    summary = (
        f"📋 ملخص البيانات:\n"
        f"👤 الاسم: {patient_name}\n"
        f"🎂 العمر: {age}\n"
        f"🏢 جهة العمل: {employer}\n"
        f"📅 تاريخ الإجازة: {date_str}\n"
        f"📆 عدد الأيام: {days}\n"
        f"🏥 المستشفى: {data['hospital_name']}\n"
        f"👨‍⚕️ الطبيب: {data['doctor_name']}\n"
        f"⚥ الجنس: {data['gender']}\n"
        f"💰 التكلفة: {price} ريال\n\n"
        f"هل البيانات صحيحة؟"
    )
    kb = yes_no_keyboard()
    kb = nav_keyboard(kb)
    await message.answer(summary, reply_markup=kb)
    await CreateReport.confirm.set()

@dp.message_handler(state=CreateReport.confirm)
async def confirm_report(message: types.Message, state: FSMContext):
    if message.text == "🏠 الرئيسية":
        await go_to_main(message, state)
        return
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
    price = data["price"]
    database.update_balance(user_id, -price, "report")

    # حفظ التقرير
    database.save_report(user_id, data["doctor_id"], data["patient_name"], data["gender"])

    # اختيار القالب المناسب وجلب الحقول المحددة
    gender = data["gender"]
    pdf_path = data["pdf_male"] if gender == "ذكر" else data["pdf_female"]
    selected_fields = database.get_pdf_config(data["doctor_id"], gender)

    # تجهيز بيانات المستخدم
    user_data = {
        "patient_name": data["patient_name"],
        "age": data["age"],
        "employer": data["employer"],
        "date": data["date"],
        "days": data["days"]
    }

    # تعبئة PDF
    try:
        if pdf_path and os.path.exists(pdf_path):
            output_stream = SmartPDFProcessor.fill_dynamic_pdf(pdf_path, user_data, selected_fields)
        else:
            # إذا لم يوجد قالب، ننشئ ملف نصي احتياطي
            output_stream = io.BytesIO()
            output_stream.write(b"Template not available. Here is your data:\n")
            for k, v in user_data.items():
                output_stream.write(f"{k}: {v}\n".encode())
            output_stream.seek(0)
    except Exception as e:
        logger.error(f"PDF generation error: {e}")
        await message.answer("❌ حدث خطأ أثناء إنشاء ملف التقرير.")
        await state.finish()
        return

    # إرسال الملف
    await bot.send_document(user_id, InputFile(output_stream, filename="تقرير_طبي.pdf"))

    # فحص الرصيد المنخفض
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
    if not is_admin_user(message.from_user.id):
        return
    await message.answer("👑 لوحة التحكم", reply_markup=admin_keyboard(message.from_user.id))

# ========== إدارة الرصيد ==========
@dp.message_handler(lambda m: m.text == "💰 إدارة الرصيد")
async def balance_management(message: types.Message):
    if not is_admin_user(message.from_user.id):
        return
    await message.answer("إدارة الرصيد:", reply_markup=balance_management_keyboard())

# إضافة رصيد
@dp.message_handler(lambda m: m.text == "➕ إضافة رصيد")
async def add_balance_start(message: types.Message):
    if not is_admin_user(message.from_user.id):
        return
    await message.answer("أرسل آيدي المستخدم:", reply_markup=cancel_keyboard())
    await AddBalance.user_id.set()

@dp.message_handler(state=AddBalance.user_id)
async def add_balance_user(message: types.Message, state: FSMContext):
    if message.text == "🏠 الرئيسية":
        await go_to_main(message, state)
        return
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
    if message.text == "🏠 الرئيسية":
        await go_to_main(message, state)
        return
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
    if message.text == "🏠 الرئيسية":
        await go_to_main(message, state)
        return
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

# خصم رصيد
@dp.message_handler(lambda m: m.text == "➖ خصم رصيد")
async def deduct_balance_start(message: types.Message):
    if not is_admin_user(message.from_user.id):
        return
    await message.answer("أرسل آيدي المستخدم:", reply_markup=cancel_keyboard())
    await DeductBalance.user_id.set()

@dp.message_handler(state=DeductBalance.user_id)
async def deduct_balance_user(message: types.Message, state: FSMContext):
    if message.text == "🏠 الرئيسية":
        await go_to_main(message, state)
        return
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
    if message.text == "🏠 الرئيسية":
        await go_to_main(message, state)
        return
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
    if message.text == "🏠 الرئيسية":
        await go_to_main(message, state)
        return
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
    if not is_admin_user(message.from_user.id):
        return
    await message.answer("أرسل آيدي المستخدم:", reply_markup=cancel_keyboard())
    await InfoUser.user_id.set()

@dp.message_handler(state=InfoUser.user_id)
async def info_user_execute(message: types.Message, state: FSMContext):
    if message.text == "🏠 الرئيسية":
        await go_to_main(message, state)
        return
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
    if not is_admin_user(message.from_user.id):
        return
    await message.answer("أرسل آيدي المستخدم للحظر:", reply_markup=cancel_keyboard())
    await BanUser.user_id.set()

@dp.message_handler(state=BanUser.user_id)
async def ban_execute(message: types.Message, state: FSMContext):
    if message.text == "🏠 الرئيسية":
        await go_to_main(message, state)
        return
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
    if not is_admin_user(message.from_user.id):
        return
    await message.answer("أرسل آيدي المستخدم لفك الحظر:", reply_markup=cancel_keyboard())
    await UnbanUser.user_id.set()

@dp.message_handler(state=UnbanUser.user_id)
async def unban_execute(message: types.Message, state: FSMContext):
    if message.text == "🏠 الرئيسية":
        await go_to_main(message, state)
        return
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
    if not is_admin_user(message.from_user.id):
        return
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("📍 عرض المناطق", "➕ إضافة منطقة", "🗑 حذف منطقة")
    kb.add("🔙 رجوع")
    await message.answer("إدارة المناطق:", reply_markup=kb)

@dp.message_handler(lambda m: m.text == "📍 عرض المناطق")
async def list_regions(message: types.Message):
    if not is_admin_user(message.from_user.id):
        return
    try:
        regions = database.get_regions()
        if not regions:
            await message.answer("لا توجد مناطق مسجلة.", reply_markup=admin_keyboard(message.from_user.id))
            return
        text = "المناطق المسجلة:\n\n"
        for r in regions:
            text += f"🆔 {r[0]} | {r[1]}\n"
        await message.answer(text, reply_markup=admin_keyboard(message.from_user.id))
    except Exception as e:
        logger.error(f"list_regions error: {e}")
        await message.answer("❌ حدث خطأ.", reply_markup=admin_keyboard(message.from_user.id))

@dp.message_handler(lambda m: m.text == "➕ إضافة منطقة")
async def add_region_start(message: types.Message):
    if not is_admin_user(message.from_user.id):
        return
    await message.answer("أرسل اسم المنطقة الجديدة:", reply_markup=cancel_keyboard())
    await AddRegion.name.set()

@dp.message_handler(state=AddRegion.name)
async def add_region_name(message: types.Message, state: FSMContext):
    if message.text == "🏠 الرئيسية":
        await go_to_main(message, state)
        return
    if message.text == "❌ إلغاء العملية":
        await cancel_operation(message, state)
        return
    name = message.text.strip()
    if name:
        try:
            database.add_region(name)
            await message.answer(f"✅ تم إضافة المنطقة '{name}'", reply_markup=admin_keyboard(message.from_user.id))
        except Exception as e:
            logger.error(f"add_region error: {e}")
            await message.answer("❌ حدث خطأ أثناء الإضافة.")
    else:
        await message.answer("❌ اسم غير صالح.")
    await state.finish()

@dp.message_handler(lambda m: m.text == "🗑 حذف منطقة")
async def delete_region_start(message: types.Message):
    if not is_admin_user(message.from_user.id):
        return
    regions = database.get_regions()
    if not regions:
        await message.answer("لا توجد مناطق مسجلة.", reply_markup=admin_keyboard(message.from_user.id))
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
            await message.answer(f"✅ تم حذف المنطقة '{region_name}'", reply_markup=admin_keyboard(message.from_user.id))
        except Exception as e:
            logger.error(f"delete_region error: {e}")
            await message.answer("❌ حدث خطأ أثناء الحذف.")
    else:
        await message.answer("❌ المنطقة غير موجودة.")
    await state.finish()

# ========== إدارة المستشفيات ==========
@dp.message_handler(lambda m: m.text == "🏥 إدارة المستشفيات")
async def manage_hospitals_menu(message: types.Message):
    if not is_admin_user(message.from_user.id):
        return
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("🏥 عرض المستشفيات", "➕ إضافة مستشفى", "🗑 حذف مستشفى")
    kb.add("🔙 رجوع")
    await message.answer("إدارة المستشفيات:", reply_markup=kb)

@dp.message_handler(lambda m: m.text == "🏥 عرض المستشفيات")
async def list_hospitals(message: types.Message):
    if not is_admin_user(message.from_user.id):
        return
    try:
        hospitals = database.get_hospitals()
        if not hospitals:
            await message.answer("لا توجد مستشفيات مسجلة.", reply_markup=admin_keyboard(message.from_user.id))
            return
        text = "المستشفيات المسجلة:\n\n"
        for h in hospitals:
            text += f"🆔 {h[0]} | {h[2]} | السعر: {h[3]} ريال\n"
        await message.answer(text, reply_markup=admin_keyboard(message.from_user.id))
    except Exception as e:
        logger.error(f"list_hospitals error: {e}")
        await message.answer("❌ حدث خطأ.")

@dp.message_handler(lambda m: m.text == "➕ إضافة مستشفى")
async def add_hospital_start(message: types.Message):
    if not is_admin_user(message.from_user.id):
        return
    regions = database.get_regions()
    if not regions:
        await message.answer("يجب إضافة منطقة أولاً.", reply_markup=admin_keyboard(message.from_user.id))
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
    if message.text == "🏠 الرئيسية":
        await go_to_main(message, state)
        return
    if message.text == "❌ إلغاء العملية":
        await cancel_operation(message, state)
        return
    name = message.text.strip()
    if name:
        try:
            data = await state.get_data()
            database.add_hospital(data["region_id"], name)
            await message.answer(f"✅ تم إضافة المستشفى '{name}'", reply_markup=admin_keyboard(message.from_user.id))
        except Exception as e:
            logger.error(f"add_hospital error: {e}")
            await message.answer("❌ حدث خطأ أثناء الإضافة.")
    else:
        await message.answer("❌ اسم غير صالح.")
    await state.finish()

@dp.message_handler(lambda m: m.text == "🗑 حذف مستشفى")
async def delete_hospital_start(message: types.Message):
    if not is_admin_user(message.from_user.id):
        return
    hospitals = database.get_hospitals()
    if not hospitals:
        await message.answer("لا توجد مستشفيات مسجلة.", reply_markup=admin_keyboard(message.from_user.id))
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
            await message.answer(f"✅ تم حذف المستشفى '{hospital_name}'", reply_markup=admin_keyboard(message.from_user.id))
        except Exception as e:
            logger.error(f"delete_hospital error: {e}")
            await message.answer("❌ حدث خطأ أثناء الحذف.")
    else:
        await message.answer("❌ المستشفى غير موجود.")
    await state.finish()

# ========== إدارة الأقسام ==========
@dp.message_handler(lambda m: m.text == "🩺 إدارة الأقسام")
async def manage_departments_menu(message: types.Message):
    if not is_admin_user(message.from_user.id):
        return
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("🩺 عرض الأقسام", "➕ إضافة قسم", "🗑 حذف قسم")
    kb.add("🔙 رجوع")
    await message.answer("إدارة الأقسام:", reply_markup=kb)

@dp.message_handler(lambda m: m.text == "🩺 عرض الأقسام")
async def list_departments(message: types.Message):
    if not is_admin_user(message.from_user.id):
        return
    try:
        departments = database.get_departments()
        if not departments:
            await message.answer("لا توجد أقسام مسجلة.", reply_markup=admin_keyboard(message.from_user.id))
            return
        text = "الأقسام المسجلة:\n\n"
        for d in departments:
            text += f"🆔 {d[0]} | {d[2]}\n"
        await message.answer(text, reply_markup=admin_keyboard(message.from_user.id))
    except Exception as e:
        logger.error(f"list_departments error: {e}")
        await message.answer("❌ حدث خطأ.")

@dp.message_handler(lambda m: m.text == "➕ إضافة قسم")
async def add_department_start(message: types.Message):
    if not is_admin_user(message.from_user.id):
        return
    regions = database.get_regions()
    if not regions:
        await message.answer("يجب إضافة منطقة أولاً.", reply_markup=admin_keyboard(message.from_user.id))
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
    if message.text == "🏠 الرئيسية":
        await go_to_main(message, state)
        return
    if message.text == "❌ إلغاء العملية":
        await cancel_operation(message, state)
        return
    name = message.text.strip()
    if name:
        try:
            data = await state.get_data()
            database.add_department(data["hospital_id"], name)
            await message.answer(f"✅ تم إضافة القسم '{name}'", reply_markup=admin_keyboard(message.from_user.id))
        except Exception as e:
            logger.error(f"add_department error: {e}")
            await message.answer("❌ حدث خطأ أثناء الإضافة.")
    else:
        await message.answer("❌ اسم غير صالح.")
    await state.finish()

@dp.message_handler(lambda m: m.text == "🗑 حذف قسم")
async def delete_department_start(message: types.Message):
    if not is_admin_user(message.from_user.id):
        return
    departments = database.get_departments()
    if not departments:
        await message.answer("لا توجد أقسام مسجلة.", reply_markup=admin_keyboard(message.from_user.id))
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
            await message.answer(f"✅ تم حذف القسم '{department_name}'", reply_markup=admin_keyboard(message.from_user.id))
        except Exception as e:
            logger.error(f"delete_department error: {e}")
            await message.answer("❌ حدث خطأ أثناء الحذف.")
    else:
        await message.answer("❌ القسم غير موجود.")
    await state.finish()

# ========== إدارة الأسعار ==========
@dp.message_handler(lambda m: m.text == "💵 إدارة الأسعار")
async def price_management_menu(message: types.Message):
    if not is_admin_user(message.from_user.id):
        return
    hospitals = database.get_hospitals()
    if not hospitals:
        await message.answer("لا توجد مستشفيات مسجلة.", reply_markup=admin_keyboard(message.from_user.id))
        return
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    for h in hospitals:
        kb.add(f"💰 {h[2]}")
    kb.add("🔙 رجوع")
    await message.answer("اختر المستشفى لتعديل سعره:", reply_markup=kb)
    await PriceManagement.choose_hospital.set()

@dp.message_handler(state=PriceManagement.choose_hospital)
async def price_choose_hospital(message: types.Message, state: FSMContext):
    if message.text == "🔙 رجوع":
        await admin_panel(message)
        await state.finish()
        return
    hospital_name = message.text.replace("💰 ", "")
    hospitals = database.get_hospitals()
    hospital_id = None
    for h in hospitals:
        if h[2] == hospital_name:
            hospital_id = h[0]
            break
    if not hospital_id:
        await message.answer("❌ مستشفى غير صحيح.")
        return
    current_price = database.get_hospital_price(hospital_id)
    await state.update_data(hospital_id=hospital_id, hospital_name=hospital_name)
    await message.answer(f"السعر الحالي لمستشفى {hospital_name} هو {current_price} ريال.\nأرسل السعر الجديد:", reply_markup=cancel_keyboard())
    await PriceManagement.new_price.set()

@dp.message_handler(state=PriceManagement.new_price)
async def price_new_price(message: types.Message, state: FSMContext):
    if message.text == "🏠 الرئيسية":
        await go_to_main(message, state)
        return
    if message.text == "❌ إلغاء العملية":
        await cancel_operation(message, state)
        return
    try:
        new_price = float(message.text)
        if new_price < 0 or new_price > 1000:
            raise ValueError
    except:
        await message.answer("❌ سعر غير صحيح. أرسل رقماً بين 0 و 1000.")
        return
    data = await state.get_data()
    database.update_hospital_price(data["hospital_id"], new_price)
    await message.answer(f"✅ تم تحديث سعر مستشفى {data['hospital_name']} إلى {new_price} ريال.", reply_markup=admin_keyboard(message.from_user.id))
    await state.finish()

# ========== إدارة الأطباء مع رفع القوالب واختيار الحقول ==========
@dp.message_handler(lambda m: m.text == "👨‍⚕️ إدارة الأطباء")
async def manage_doctors_menu(message: types.Message):
    if not is_admin_user(message.from_user.id):
        return
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("👨‍⚕️ عرض الأطباء", "➕ إضافة طبيب", "🗑 حذف طبيب")
    kb.add("🔙 رجوع")
    await message.answer("إدارة الأطباء:", reply_markup=kb)

@dp.message_handler(lambda m: m.text == "👨‍⚕️ عرض الأطباء")
async def list_doctors(message: types.Message):
    if not is_admin_user(message.from_user.id):
        return
    try:
        doctors = database.get_doctors()
        if not doctors:
            await message.answer("لا يوجد أطباء مسجلين.", reply_markup=admin_keyboard(message.from_user.id))
            return
        text = "الأطباء المسجلون:\n\n"
        for doc in doctors:
            text += f"🆔 {doc[0]} | {doc[3]} - {doc[4]}\n"
        await message.answer(text, reply_markup=admin_keyboard(message.from_user.id))
    except Exception as e:
        logger.error(f"list_doctors error: {e}")
        await message.answer("❌ حدث خطأ.")

@dp.message_handler(lambda m: m.text == "➕ إضافة طبيب")
async def add_doctor_start(message: types.Message):
    if not is_admin_user(message.from_user.id):
        return
    regions = database.get_regions()
    if not regions:
        await message.answer("يجب إضافة منطقة أولاً.", reply_markup=admin_keyboard(message.from_user.id))
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
    await state.update_data(region_id=region_id, region_name=region_name)
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
    await state.update_data(hospital_id=hospital_id, hospital_name=hospital_name)
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
    await state.update_data(department_id=department_id, department_name=department_name)
    await message.answer("أرسل اسم الطبيب:", reply_markup=cancel_keyboard())
    await AddDoctor.name.set()

@dp.message_handler(state=AddDoctor.name)
async def add_doctor_name(message: types.Message, state: FSMContext):
    if message.text == "🏠 الرئيسية":
        await go_to_main(message, state)
        return
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
    if message.text == "🏠 الرئيسية":
        await go_to_main(message, state)
        return
    if message.text == "❌ إلغاء العملية":
        await cancel_operation(message, state)
        return
    title = message.text.strip()
    if not title:
        await message.answer("❌ مسمى غير صالح.")
        return
    data = await state.get_data()
    # إضافة الطبيب بدون ملفات PDF
    doctor_id = database.add_doctor(
        data["department_id"],
        data["name"],
        title,
        None,  # pdf_male
        None   # pdf_female
    )
    await message.answer(
        f"✅ تم إضافة الطبيب '{data['name']}' بنجاح.\n"
        "يمكنك الآن رفع القوالب الخاصة به من خلال زر '📄 رفع قالب طبي' في لوحة التحكم.",
        reply_markup=admin_keyboard(message.from_user.id)
    )
    await state.finish()

@dp.message_handler(lambda m: m.text == "🗑 حذف طبيب")
async def delete_doctor_start(message: types.Message):
    if not is_admin_user(message.from_user.id):
        return
    doctors = database.get_doctors()
    if not doctors:
        await message.answer("لا يوجد أطباء مسجلين.", reply_markup=admin_keyboard(message.from_user.id))
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
            await message.answer(f"✅ تم حذف الطبيب '{doctor_name}'", reply_markup=admin_keyboard(message.from_user.id))
        except Exception as e:
            logger.error(f"delete_doctor error: {e}")
            await message.answer("❌ حدث خطأ أثناء الحذف.")
    else:
        await message.answer("❌ الطبيب غير موجود.")
    await state.finish()

# ========== رفع قالب طبي ==========
@dp.message_handler(lambda m: m.text == "📄 رفع قالب طبي")
async def upload_template_start(message: types.Message):
    if not is_admin_user(message.from_user.id):
        return
    await show_region_selection(message, None)
    await UploadTemplate.choose_region.set()

@dp.message_handler(state=UploadTemplate.choose_region)
async def upload_template_region(message: types.Message, state: FSMContext):
    if message.text == "🏠 الرئيسية":
        await go_to_main(message, state)
        return
    if message.text == "🔙 رجوع":
        await message.answer("أنت في البداية.")
        return

    region_name = message.text.replace("📍 ", "")
    region_id = None
    for r in database.get_regions():
        if r[1] == region_name:
            region_id = r[0]
            break

    if not region_id:
        await message.answer("❌ اختيار غير صحيح.")
        return

    await state.update_data(region_id=region_id)
    await show_hospital_selection(message, state)
    await UploadTemplate.choose_hospital.set()

@dp.message_handler(state=UploadTemplate.choose_hospital)
async def upload_template_hospital(message: types.Message, state: FSMContext):
    if message.text == "🏠 الرئيسية":
        await go_to_main(message, state)
        return
    if message.text == "🔙 رجوع":
        await state.set_state(UploadTemplate.choose_region)
        await show_region_selection(message, state)
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

    await state.update_data(hospital_id=hospital_id, hospital_name=hospital_name)
    await show_department_selection(message, state)
    await UploadTemplate.choose_department.set()

@dp.message_handler(state=UploadTemplate.choose_department)
async def upload_template_department(message: types.Message, state: FSMContext):
    if message.text == "🏠 الرئيسية":
        await go_to_main(message, state)
        return
    if message.text == "🔙 رجوع":
        await state.set_state(UploadTemplate.choose_hospital)
        await show_hospital_selection(message, state)
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

    await state.update_data(department_id=department_id)
    await show_doctor_selection(message, state)
    await UploadTemplate.choose_doctor.set()

@dp.message_handler(state=UploadTemplate.choose_doctor)
async def upload_template_doctor(message: types.Message, state: FSMContext):
    if message.text == "🏠 الرئيسية":
        await go_to_main(message, state)
        return
    if message.text == "🔙 رجوع":
        await state.set_state(UploadTemplate.choose_department)
        await show_department_selection(message, state)
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

    await state.update_data(doctor_id=doctor_id, doctor_name=doctor_name)
    await show_gender_selection(message, state)
    await UploadTemplate.choose_gender.set()

@dp.message_handler(state=UploadTemplate.choose_gender)
async def upload_template_gender(message: types.Message, state: FSMContext):
    if message.text == "🏠 الرئيسية":
        await go_to_main(message, state)
        return
    if message.text == "🔙 رجوع":
        await state.set_state(UploadTemplate.choose_doctor)
        await show_doctor_selection(message, state)
        return

    gender_map = {"👨 ذكر": "ذكر", "👩 أنثى": "أنثى"}
    if message.text not in gender_map:
        await message.answer("❌ اختيار غير صحيح.")
        return
    gender = gender_map[message.text]
    await state.update_data(gender=gender)

    await message.answer("الرجاء رفع ملف PDF الخاص بهذا الطبيب لهذا الجنس:", reply_markup=cancel_keyboard())
    await UploadTemplate.upload_file.set()

@dp.message_handler(content_types=['document'], state=UploadTemplate.upload_file)
async def upload_template_file(message: types.Message, state: FSMContext):
    if message.text == "🏠 الرئيسية":
        await go_to_main(message, state)
        return
    if message.text == "❌ إلغاء العملية":
        await cancel_operation(message, state)
        return
    if not message.document or not message.document.file_name.endswith('.pdf'):
        await message.answer("❌ يرجى رفع ملف PDF صالح.")
        return

    data = await state.get_data()
    # الحصول على أسماء المنطقة والمستشفى والقسم من قاعدة البيانات
    region = database.get_region(data["region_id"])
    region_name = region[1] if region else "unknown"
    hospital_name = data["hospital_name"]
    dept = database.get_department(data["department_id"])
    department_name = dept[2] if dept else "unknown"

    # بناء مسار الحفظ
    pdf_path = get_template_path(region_name, hospital_name, department_name, data["gender"])

    # تحميل الملف
    file_info = await bot.get_file(message.document.file_id)
    file_bytes = await bot.download_file(file_info.file_path)

    # حفظ الملف محلياً
    with open(pdf_path, "wb") as f:
        f.write(file_bytes.getvalue())

    # تحليل الحقول
    fields = SmartPDFProcessor.analyze_pdf(pdf_path)

    if not fields:
        # لا توجد حقول تفاعلية، نخزن الملف وننهي
        database.update_doctor_pdf(data["doctor_id"], data["gender"], pdf_path)
        database.save_pdf_config(data["doctor_id"], data["gender"], [])  # تكوين فارغ
        await message.answer("✅ تم رفع القالب بنجاح (بدون حقول تفاعلية).", reply_markup=admin_keyboard(message.from_user.id))
        await state.finish()
        return

    # تخزين البيانات للمرحلة التالية
    await state.update_data(pdf_path=pdf_path, fields=fields, selected_fields=[])

    # عرض الحقول لاختيارها
    gender_code = "male" if data["gender"] == "ذكر" else "female"
    await message.answer("🎯 اختر الحقول التي تود تعبئتها في هذا القالب:",
                         reply_markup=get_fields_keyboard(fields, [], gender_code))
    await UploadTemplate.confirm_fields.set()

# ========== معالجات اختيار الحقول (toggle / save) ==========
@dp.callback_query_handler(lambda c: c.data.startswith('toggle_'), state=UploadTemplate.confirm_fields)
async def toggle_field(callback_query: types.CallbackQuery, state: FSMContext):
    parts = callback_query.data.split('_', 2)
    if len(parts) < 3:
        await callback_query.answer("خطأ في البيانات")
        return
    _, gender_code, field_name = parts  # gender_code = 'male' أو 'female'
    data = await state.get_data()
    selected = data.get("selected_fields", [])
    if field_name in selected:
        selected.remove(field_name)
    else:
        selected.append(field_name)
    await state.update_data(selected_fields=selected)
    keyboard = get_fields_keyboard(data["fields"], selected, gender_code)
    await callback_query.message.edit_reply_markup(reply_markup=keyboard)
    await callback_query.answer()

@dp.callback_query_handler(lambda c: c.data.startswith('save_'), state=UploadTemplate.confirm_fields)
async def save_fields(callback_query: types.CallbackQuery, state: FSMContext):
    parts = callback_query.data.split('_')
    if len(parts) != 2:
        await callback_query.answer("خطأ في البيانات")
        return
    gender_code = parts[1]  # 'male' أو 'female'
    data = await state.get_data()
    doctor_id = data["doctor_id"]
    gender_ar = "ذكر" if gender_code == "male" else "أنثى"
    selected = data.get("selected_fields", [])
    # حفظ التكوين
    database.save_pdf_config(doctor_id, gender_ar, selected)
    # تحديث مسار PDF
    database.update_doctor_pdf(doctor_id, gender_ar, data["pdf_path"])
    await callback_query.message.edit_text(f"✅ تم رفع القالب للطبيب ({gender_ar}) بنجاح.")
    await state.finish()
    await callback_query.answer()

# ========== الإحصائيات ==========
@dp.message_handler(lambda m: m.text == "📊 الإحصائيات")
async def stats(message: types.Message):
    if not is_admin_user(message.from_user.id):
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
        await message.answer(text, reply_markup=admin_keyboard(message.from_user.id))
    except Exception as e:
        logger.error(f"stats error: {e}")
        await message.answer("❌ حدث خطأ في جلب الإحصائيات.", reply_markup=admin_keyboard(message.from_user.id))

# ========== الإشعارات ==========
@dp.message_handler(lambda m: m.text == "📢 الإشعارات")
async def notifications_menu(message: types.Message):
    if not is_admin_user(message.from_user.id):
        return
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("📢 إشعار لمستخدم", "📣 إشعار جماعي")
    kb.add("🔙 رجوع")
    await message.answer("الإشعارات:", reply_markup=kb)

@dp.message_handler(lambda m: m.text == "📢 إشعار لمستخدم")
async def notify_user_start(message: types.Message):
    if not is_admin_user(message.from_user.id):
        return
    await message.answer("أرسل آيدي المستخدم:", reply_markup=cancel_keyboard())
    await NotifyUser.user_id.set()

@dp.message_handler(state=NotifyUser.user_id)
async def notify_user_get_id(message: types.Message, state: FSMContext):
    if message.text == "🏠 الرئيسية":
        await go_to_main(message, state)
        return
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
    if message.text == "🏠 الرئيسية":
        await go_to_main(message, state)
        return
    if message.text == "❌ إلغاء العملية":
        await cancel_operation(message, state)
        return
    await state.update_data(text=message.text)
    await message.answer("هل تريد إرسال الإشعار؟", reply_markup=yes_no_keyboard())
    await NotifyUser.confirm.set()

@dp.message_handler(state=NotifyUser.confirm)
async def notify_user_confirm(message: types.Message, state: FSMContext):
    if message.text == "🏠 الرئيسية":
        await go_to_main(message, state)
        return
    if message.text == "❌ إلغاء العملية":
        await cancel_operation(message, state)
        return
    data = await state.get_data()
    if message.text == "✅ نعم":
        try:
            await bot.send_message(data["user_id"], data["text"])
            await message.answer("✅ تم إرسال الإشعار.", reply_markup=admin_keyboard(message.from_user.id))
        except Exception as e:
            logger.error(f"notify error: {e}")
            await message.answer("❌ فشل إرسال الإشعار.", reply_markup=admin_keyboard(message.from_user.id))
    else:
        await message.answer("❌ تم إلغاء الإرسال.", reply_markup=admin_keyboard(message.from_user.id))
    await state.finish()

@dp.message_handler(lambda m: m.text == "📣 إشعار جماعي")
async def broadcast_start(message: types.Message):
    if not is_admin_user(message.from_user.id):
        return
    await message.answer("أرسل نص الرسالة الجماعية:", reply_markup=cancel_keyboard())
    await Broadcast.message.set()

@dp.message_handler(state=Broadcast.message)
async def broadcast_message(message: types.Message, state: FSMContext):
    if message.text == "🏠 الرئيسية":
        await go_to_main(message, state)
        return
    if message.text == "❌ إلغاء العملية":
        await cancel_operation(message, state)
        return
    await state.update_data(text=message.text)
    await message.answer("هل تريد إرسال الإشعار لكل المستخدمين النشطين؟", reply_markup=yes_no_keyboard())
    await Broadcast.confirm.set()

@dp.message_handler(state=Broadcast.confirm)
async def broadcast_confirm(message: types.Message, state: FSMContext):
    if message.text == "🏠 الرئيسية":
        await go_to_main(message, state)
        return
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
        await message.answer(f"✅ تم الإرسال إلى {count} مستخدم.", reply_markup=admin_keyboard(message.from_user.id))
    else:
        await message.answer("❌ تم إلغاء العملية.", reply_markup=admin_keyboard(message.from_user.id))
    await state.finish()
    
# ========== إدارة المشرفين ==========
@dp.message_handler(lambda m: m.text == "👥 إدارة المشرفين")
async def manage_admins_menu(message: types.Message):
    if not is_developer(message.from_user.id):
        return
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("👥 عرض المشرفين", "➕ إضافة مشرف", "🗑 حذف مشرف")
    kb.add("🔙 رجوع")
    await message.answer("إدارة المشرفين:", reply_markup=kb)

@dp.message_handler(lambda m: m.text == "👥 عرض المشرفين")
async def list_admins(message: types.Message):
    if not is_developer(message.from_user.id):
        return
    admins = database.get_all_admins()
    if not admins:
        await message.answer("لا يوجد مشرفين حالياً.", reply_markup=admin_keyboard(message.from_user.id))
        return
    text = "📋 قائمة المشرفين:\n\n"
    for admin in admins:
        user_id, username, added_at, added_by = admin
        text += f"🆔 {user_id}\n"
        text += f"👤 {username if username else '—'}\n"
        text += f"📅 أضيف في: {added_at}\n"
        text += f"➕ بواسطة: {added_by}\n\n"
    await message.answer(text, reply_markup=admin_keyboard(message.from_user.id))

@dp.message_handler(lambda m: m.text == "➕ إضافة مشرف")
async def add_admin_start(message: types.Message):
    if not is_developer(message.from_user.id):
        return
    await message.answer("أرسل آيدي المستخدم الذي تريد جعله مشرفاً:", reply_markup=cancel_keyboard())
    await AddAdmin.user_id.set()

@dp.message_handler(state=AddAdmin.user_id)
async def add_admin_get_id(message: types.Message, state: FSMContext):
    if message.text == "🏠 الرئيسية":
        await go_to_main(message, state)
        return
    if message.text == "❌ إلغاء العملية":
        await cancel_operation(message, state)
        return
    if not message.text.isdigit():
        await message.answer("❌ آيدي غير صحيح.")
        return
    user_id = int(message.text)
    user = database.get_user(user_id)
    if not user:
        await message.answer("❌ هذا المستخدم غير مسجل في البوت.")
        return
    if is_developer(user_id):
        await message.answer("❌ هذا المستخدم هو المطور الأساسي.")
        return
    if database.is_admin(user_id):
        await message.answer("❌ هذا المستخدم مشرف بالفعل.")
        return
    await state.update_data(target_user_id=user_id, target_username=user[2])
    await message.answer(f"هل أنت متأكد من إضافة {user[2]} (آيدي: {user_id}) كمشرف؟", reply_markup=yes_no_keyboard())
    await AddAdmin.confirm.set()

@dp.message_handler(state=AddAdmin.confirm)
async def add_admin_confirm(message: types.Message, state: FSMContext):
    if message.text == "🏠 الرئيسية":
        await go_to_main(message, state)
        return
    if message.text == "❌ إلغاء العملية":
        await cancel_operation(message, state)
        return
    if message.text == "✅ نعم":
        data = await state.get_data()
        database.add_admin(data["target_user_id"], message.from_user.id)
        await message.answer(f"✅ تمت إضافة {data['target_username']} كمشرف بنجاح.", reply_markup=admin_keyboard(message.from_user.id))
        try:
            await bot.send_message(data["target_user_id"], "🎉 لقد تمت ترقيتك إلى مشرف في البوت. الآن يمكنك استخدام لوحة التحكم.")
        except:
            pass
    else:
        await message.answer("❌ تم الإلغاء.", reply_markup=admin_keyboard(message.from_user.id))
    await state.finish()

@dp.message_handler(lambda m: m.text == "🗑 حذف مشرف")
async def remove_admin_start(message: types.Message):
    if not is_developer(message.from_user.id):
        return
    admins = database.get_all_admins()
    if not admins:
        await message.answer("لا يوجد مشرفين حالياً.", reply_markup=admin_keyboard(message.from_user.id))
        return
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    for admin in admins:
        username = admin[1] if admin[1] else f"آيدي {admin[0]}"
        kb.add(f"🗑 {username} (ID: {admin[0]})")
    kb.add("🔙 رجوع")
    await message.answer("اختر المشرف الذي تريد حذفه:", reply_markup=kb)
    await RemoveAdmin.choose.set()

@dp.message_handler(state=RemoveAdmin.choose)
async def remove_admin_choose(message: types.Message, state: FSMContext):
    if message.text == "🔙 رجوع":
        await manage_admins_menu(message)
        await state.finish()
        return
    import re
    match = re.search(r'ID: (\d+)', message.text)
    if not match:
        await message.answer("❌ اختيار غير صحيح.")
        return
    user_id = int(match.group(1))
    await state.update_data(target_user_id=user_id)
    await message.answer(f"هل أنت متأكد من حذف المشرف (آيدي: {user_id})؟", reply_markup=yes_no_keyboard())
    await RemoveAdmin.confirm.set()

@dp.message_handler(state=RemoveAdmin.confirm)
async def remove_admin_confirm(message: types.Message, state: FSMContext):
    if message.text == "🏠 الرئيسية":
        await go_to_main(message, state)
        return
    if message.text == "❌ إلغاء العملية":
        await cancel_operation(message, state)
        return
    if message.text == "✅ نعم":
        data = await state.get_data()
        database.remove_admin(data["target_user_id"])
        await message.answer("✅ تم حذف المشرف بنجاح.", reply_markup=admin_keyboard(message.from_user.id))
        try:
            await bot.send_message(data["target_user_id"], "تم إلغاء صلاحية المشرف عن حسابك.")
        except:
            pass
    else:
        await message.answer("❌ تم الإلغاء.", reply_markup=admin_keyboard(message.from_user.id))
    await state.finish()

# ========== العودة للقائمة الرئيسية ==========
@dp.message_handler(lambda m: m.text == "🔙 رجوع", state="*")
async def back_main(message: types.Message, state: FSMContext):
    if await state.get_state() is not None:
        await state.finish()
        await message.answer("❌ تم إلغاء العملية للرجوع.")
    if is_admin_user(message.from_user.id):
        await message.answer("القائمة الرئيسية", reply_markup=admin_keyboard(message.from_user.id))
    else:
        await message.answer("القائمة الرئيسية", reply_markup=main_keyboard(False))

if __name__ == "__main__":
    logger.info("Starting bot...")
    executor.start_polling(dp, skip_updates=True)
