import logging
import os
import io
import fitz  # PyMuPDF
from aiogram import Bot, Dispatcher, executor, types
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InputFile
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.contrib.fsm_storage.memory import MemoryStorage
import database

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = str(os.getenv("ADMIN_ID")).strip()

logging.basicConfig(level=logging.INFO)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot, storage=MemoryStorage())

database.init_db()

# ================= دوال مساعدة للوحات المفاتيح =================
def main_keyboard(is_admin=False):
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("💰 رصيدي", "📄 إصدار تقرير")
    if is_admin:
        kb.add("👑 لوحة المطور")
    return kb

def admin_keyboard():
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("➕ إضافة رصيد", "➖ خصم رصيد")
    kb.add("🚫 حظر مستخدم", "🔓 فك حظر")
    kb.add("👤 معلومات مستخدم")
    kb.add("📢 إشعار لمستخدم", "📣 إشعار جماعي")
    kb.add("⚠ الحسابات منخفضة الرصيد")
    kb.add("🌍 إدارة المناطق", "🏥 إدارة المستشفيات")
    kb.add("🩺 إدارة الأقسام", "👨‍⚕️ إدارة الأطباء")
    kb.add("🔙 رجوع", "❌ إلغاء العملية")
    return kb

def yes_no_keyboard():
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("✅ نعم", "❌ لا")
    return kb

# ================= دالة لإرجاع اللوحة المناسبة حسب حالة المستخدم =================
def get_correct_keyboard(user_id):
    is_admin = str(user_id) == ADMIN_ID
    return admin_keyboard() if is_admin else main_keyboard(False)

# ================= تعريف الحالات (States) =================
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

class CreateReport(StatesGroup):
    choose_region = State()
    choose_hospital = State()
    choose_department = State()
    choose_doctor = State()
    choose_gender = State()
    # بيانات المريض
    patient_name = State()
    patient_file_no = State()
    patient_age = State()
    patient_nationality = State()
    patient_employer = State()
    clinic_date = State()
    admission_date = State()
    discharge_date = State()
    leave_days = State()
    diagnosis = State()          # يمكن جلبها افتراضياً
    recommendations = State()     # يمكن جلبها افتراضياً
    confirm_data = State()

# حالات إدارة المناطق
class AddRegion(StatesGroup):
    name = State()

class DeleteRegion(StatesGroup):
    choose = State()

# حالات إدارة المستشفيات
class AddHospital(StatesGroup):
    region = State()
    name = State()

class DeleteHospital(StatesGroup):
    choose = State()

# حالات إدارة الأقسام
class AddDepartment(StatesGroup):
    hospital = State()
    name = State()

class DeleteDepartment(StatesGroup):
    choose = State()

# حالات إدارة الأطباء
class AddDoctor(StatesGroup):
    department = State()
    name = State()
    specialization = State()
    pdf_male = State()
    pdf_female = State()

class DeleteDoctor(StatesGroup):
    choose = State()

# ================= دالة فحص الرصيد المنخفض =================
async def check_low_balance(user_id):
    balance = database.get_balance(user_id)
    if balance < 3:
        try:
            await bot.send_message(user_id, "⚠ رصيدك أوشك على الانتهاء.\nالرجاء إعادة الشحن لإصدار تقاريرك بنجاح ✅")
        except:
            pass

# ================= معالج الإلغاء (معدل) =================
@dp.message_handler(lambda m: m.text == "❌ إلغاء العملية", state="*")
async def cancel_operation(message: types.Message, state: FSMContext):
    if await state.get_state() is None:
        await message.answer("لا توجد عملية لإلغائها.")
        return
    await state.finish()
    # إرجاع اللوحة المناسبة
    await message.answer("✅ تم إلغاء العملية.", reply_markup=get_correct_keyboard(message.from_user.id))

# ================= بداية البوت =================
@dp.message_handler(commands=['start'])
async def start(message: types.Message):
    user_id = message.from_user.id
    username = message.from_user.username or "NoUsername"
    is_admin = 1 if str(user_id) == ADMIN_ID else 0
    database.add_user(user_id, username, is_admin)
    await message.answer("🩺 أهلاً بك في نظام التقارير الطبية", reply_markup=main_keyboard(is_admin))

# ================= عرض الرصيد =================
@dp.message_handler(lambda m: m.text == "💰 رصيدي")
async def balance_handler(message: types.Message):
    user = database.get_user(message.from_user.id)
    if user and user[5] == 1:
        await message.answer("🚫 حسابك محظور.")
        return
    balance = database.get_balance(message.from_user.id)
    await message.answer(f"رصيدك الحالي: {balance} ريال", reply_markup=get_correct_keyboard(message.from_user.id))

# ================= إصدار تقرير (محدث مع إدخال البيانات) =================
@dp.message_handler(lambda m: m.text == "📄 إصدار تقرير")
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
        kb.add(f"🌍 {r[1]}")
    kb.add("❌ إلغاء العملية")
    await message.answer("اختر المنطقة:", reply_markup=kb)
    await CreateReport.choose_region.set()

@dp.message_handler(state=CreateReport.choose_region)
async def choose_region_report(message: types.Message, state: FSMContext):
    if message.text == "❌ إلغاء العملية":
        await cancel_operation(message, state)
        return

    region_name = message.text.replace("🌍 ", "")
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
        await message.answer("لا توجد مستشفيات في هذه المنطقة.")
        await state.finish()
        return

    await state.update_data(region_id=region_id)

    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    for h in hospitals:
        kb.add(f"🏥 {h[2]}")
    kb.add("❌ إلغاء العملية")
    await message.answer("اختر المستشفى:", reply_markup=kb)
    await CreateReport.choose_hospital.set()

@dp.message_handler(state=CreateReport.choose_hospital)
async def choose_hospital_report(message: types.Message, state: FSMContext):
    if message.text == "❌ إلغاء العملية":
        await cancel_operation(message, state)
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
        await message.answer("لا توجد أقسام في هذا المستشفى.")
        await state.finish()
        return

    await state.update_data(hospital_id=hospital_id, hospital_name=hospital_name)

    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    for d in departments:
        kb.add(f"🩺 {d[2]}")
    kb.add("❌ إلغاء العملية")
    await message.answer("اختر القسم:", reply_markup=kb)
    await CreateReport.choose_department.set()

@dp.message_handler(state=CreateReport.choose_department)
async def choose_department_report(message: types.Message, state: FSMContext):
    if message.text == "❌ إلغاء العملية":
        await cancel_operation(message, state)
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
        await message.answer("لا يوجد أطباء في هذا القسم.")
        await state.finish()
        return

    await state.update_data(department_id=department_id)

    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    for doc in doctors:
        kb.add(f"👨‍⚕️ {doc[3]}")
    kb.add("❌ إلغاء العملية")
    await message.answer("اختر الطبيب:", reply_markup=kb)
    await CreateReport.choose_doctor.set()

@dp.message_handler(state=CreateReport.choose_doctor)
async def choose_doctor_report(message: types.Message, state: FSMContext):
    if message.text == "❌ إلغاء العملية":
        await cancel_operation(message, state)
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
    # حفظ بيانات الطبيب
    await state.update_data(doctor_id=doctor_id, doctor_name=doctor_name,
                            specialization=doctor[3],
                            pdf_male=doctor[4], pdf_female=doctor[5])

    # اختيار الجنس
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("ذكر", "أنثى")
    kb.add("❌ إلغاء العملية")
    await message.answer("اختر جنس المريض:", reply_markup=kb)
    await CreateReport.choose_gender.set()

@dp.message_handler(state=CreateReport.choose_gender)
async def choose_gender_report(message: types.Message, state: FSMContext):
    if message.text == "❌ إلغاء العملية":
        await cancel_operation(message, state)
        return

    gender = message.text
    if gender not in ["ذكر", "أنثى"]:
        await message.answer("❌ اختيار غير صحيح.")
        return

    await state.update_data(gender=gender)

    # بدء إدخال بيانات المريض
    await message.answer("أدخل اسم المريض الكامل:")
    await CreateReport.patient_name.set()

@dp.message_handler(state=CreateReport.patient_name)
async def enter_patient_name(message: types.Message, state: FSMContext):
    if message.text == "❌ إلغاء العملية":
        await cancel_operation(message, state)
        return
    await state.update_data(patient_name=message.text)
    await message.answer("أدخل رقم الملف الطبي:")
    await CreateReport.patient_file_no.set()

@dp.message_handler(state=CreateReport.patient_file_no)
async def enter_file_no(message: types.Message, state: FSMContext):
    if message.text == "❌ إلغاء العملية":
        await cancel_operation(message, state)
        return
    await state.update_data(file_no=message.text)
    await message.answer("أدخل العمر:")
    await CreateReport.patient_age.set()

@dp.message_handler(state=CreateReport.patient_age)
async def enter_age(message: types.Message, state: FSMContext):
    if message.text == "❌ إلغاء العملية":
        await cancel_operation(message, state)
        return
    await state.update_data(age=message.text)
    await message.answer("أدخل الجنسية:")
    await CreateReport.patient_nationality.set()

@dp.message_handler(state=CreateReport.patient_nationality)
async def enter_nationality(message: types.Message, state: FSMContext):
    if message.text == "❌ إلغاء العملية":
        await cancel_operation(message, state)
        return
    await state.update_data(nationality=message.text)
    await message.answer("أدخل جهة العمل:")
    await CreateReport.patient_employer.set()

@dp.message_handler(state=CreateReport.patient_employer)
async def enter_employer(message: types.Message, state: FSMContext):
    if message.text == "❌ إلغاء العملية":
        await cancel_operation(message, state)
        return
    await state.update_data(employer=message.text)
    await message.answer("أدخل تاريخ مراجعة العيادة (بصيغة YYYY-MM-DD):")
    await CreateReport.clinic_date.set()

@dp.message_handler(state=CreateReport.clinic_date)
async def enter_clinic_date(message: types.Message, state: FSMContext):
    if message.text == "❌ إلغاء العملية":
        await cancel_operation(message, state)
        return
    # يمكن التحقق من صيغة التاريخ
    await state.update_data(clinic_date=message.text)
    await message.answer("أدخل تاريخ الدخول للمستشفى (YYYY-MM-DD):")
    await CreateReport.admission_date.set()

@dp.message_handler(state=CreateReport.admission_date)
async def enter_admission_date(message: types.Message, state: FSMContext):
    if message.text == "❌ إلغاء العملية":
        await cancel_operation(message, state)
        return
    await state.update_data(admission_date=message.text)
    await message.answer("أدخل تاريخ الخروج من المستشفى (YYYY-MM-DD):")
    await CreateReport.discharge_date.set()

@dp.message_handler(state=CreateReport.discharge_date)
async def enter_discharge_date(message: types.Message, state: FSMContext):
    if message.text == "❌ إلغاء العملية":
        await cancel_operation(message, state)
        return
    await state.update_data(discharge_date=message.text)
    await message.answer("أدخل عدد أيام الإجازة المرضية:")
    await CreateReport.leave_days.set()

@dp.message_handler(state=CreateReport.leave_days)
async def enter_leave_days(message: types.Message, state: FSMContext):
    if message.text == "❌ إلغاء العملية":
        await cancel_operation(message, state)
        return
    await state.update_data(leave_days=message.text)

    # يمكننا هنا عرض البيانات للتأكيد
    data = await state.get_data()
    summary = (
        f"المراجعة النهائية للبيانات:\n"
        f"الاسم: {data['patient_name']}\n"
        f"رقم الملف: {data['file_no']}\n"
        f"العمر: {data['age']}\n"
        f"الجنسية: {data['nationality']}\n"
        f"جهة العمل: {data['employer']}\n"
        f"تاريخ العيادة: {data['clinic_date']}\n"
        f"تاريخ الدخول: {data['admission_date']}\n"
        f"تاريخ الخروج: {data['discharge_date']}\n"
        f"عدد الأيام: {data['leave_days']}\n"
        f"المستشفى: {data['hospital_name']}\n"
        f"الطبيب: {data['doctor_name']}\n"
        f"التخصص: {data['specialization']}\n"
        f"الجنس: {data['gender']}"
    )
    kb = yes_no_keyboard()
    kb.add("❌ إلغاء العملية")
    await message.answer(summary + "\n\nهل البيانات صحيحة؟", reply_markup=kb)
    await CreateReport.confirm_data.set()

@dp.message_handler(state=CreateReport.confirm_data)
async def confirm_data(message: types.Message, state: FSMContext):
    if message.text == "❌ إلغاء العملية":
        await cancel_operation(message, state)
        return
    if message.text != "✅ نعم":
        await message.answer("تم الإلغاء.", reply_markup=get_correct_keyboard(message.from_user.id))
        await state.finish()
        return

    # تأكيد البيانات وبدء معالجة PDF
    data = await state.get_data()
    user_id = message.from_user.id

    # خصم الرصيد
    database.update_balance(user_id, -3, "report")

    # حفظ التقرير في قاعدة البيانات
    database.save_report(user_id, data["hospital_name"], data["doctor_name"], data["patient_name"])

    # تحديد قالب PDF المناسب
    pdf_file_id = data["pdf_male"] if data["gender"] == "ذكر" else data["pdf_female"]

    # تحميل الملف من تليجرام
    try:
        file_info = await bot.get_file(pdf_file_id)
        downloaded_file = await bot.download_file(file_info.file_path)
        pdf_bytes = downloaded_file.getvalue()
    except Exception as e:
        await message.answer(f"حدث خطأ في تحميل قالب PDF: {e}")
        await state.finish()
        return

    # فتح PDF وتعبئة الحقول
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        for page in doc:
            widgets = page.widgets()
            if widgets:
                for w in widgets:
                    # هنا سنقوم بتعبئة الحقول بناءً على أسماء الحقول التي ستزودني بها
                    # مثال:
                    if w.field_name == "full_name":
                        w.field_value = data["patient_name"]
                        w.update()
                    elif w.field_name == "file_no":
                        w.field_value = data["file_no"]
                        w.update()
                    # أضف باقي الحقول حسب ما سترسله
        # حفظ الملف المعبأ في ذاكرة BytesIO
        output_stream = io.BytesIO()
        doc.save(output_stream)
        doc.close()
        output_stream.seek(0)
    except Exception as e:
        await message.answer(f"حدث خطأ في تعبئة PDF: {e}")
        await state.finish()
        return

    # إرسال الملف المعبأ
    await bot.send_document(user_id, InputFile(output_stream, filename="تقرير_طبي.pdf"))

    # إشعار الرصيد المنخفض
    await check_low_balance(user_id)

    await message.answer("✅ تم إنشاء التقرير بنجاح.", reply_markup=get_correct_keyboard(user_id))
    await state.finish()

# ================= لوحة المطور =================
@dp.message_handler(lambda m: m.text == "👑 لوحة المطور")
async def admin_panel(message: types.Message):
    if str(message.from_user.id) != ADMIN_ID:
        return
    await message.answer("👑 لوحة تحكم المطور", reply_markup=admin_keyboard())

# ================= إضافة رصيد =================
@dp.message_handler(lambda m: m.text == "➕ إضافة رصيد")
async def add_balance_start(message: types.Message):
    if str(message.from_user.id) != ADMIN_ID:
        return
    await message.answer("أرسل آيدي المستخدم:")
    await AddBalance.user_id.set()

@dp.message_handler(state=AddBalance.user_id)
async def add_balance_user(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("❌ آيدي غير صحيح.")
        return
    await state.update_data(user_id=int(message.text))
    await message.answer("أرسل المبلغ:")
    await AddBalance.amount.set()

@dp.message_handler(state=AddBalance.amount)
async def add_balance_amount(message: types.Message, state: FSMContext):
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
    data = await state.get_data()
    user_id = data["user_id"]
    amount = data["amount"]

    database.update_balance(user_id, amount, "add")

    if message.text == "✅ نعم":
        try:
            await bot.send_message(
                user_id,
                f"💰 تم إضافة {amount} ريال إلى حسابك.\nرصيدك الحالي: {database.get_balance(user_id)} ريال"
            )
        except:
            pass

    await message.answer("✅ تم تنفيذ العملية.", reply_markup=admin_keyboard())
    await state.finish()

# ================= خصم رصيد =================
@dp.message_handler(lambda m: m.text == "➖ خصم رصيد")
async def deduct_balance_start(message: types.Message):
    if str(message.from_user.id) != ADMIN_ID:
        return
    await message.answer("أرسل آيدي المستخدم:")
    await DeductBalance.user_id.set()

@dp.message_handler(state=DeductBalance.user_id)
async def deduct_balance_user(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("❌ آيدي غير صحيح.")
        return
    await state.update_data(user_id=int(message.text))
    await message.answer("أرسل المبلغ:")
    await DeductBalance.amount.set()

@dp.message_handler(state=DeductBalance.amount)
async def deduct_balance_amount(message: types.Message, state: FSMContext):
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
    data = await state.get_data()
    user_id = data["user_id"]
    amount = data["amount"]

    database.update_balance(user_id, -amount, "deduct")

    if message.text == "✅ نعم":
        try:
            await bot.send_message(
                user_id,
                f"⚠ تم خصم {amount} ريال من حسابك.\nرصيدك الحالي: {database.get_balance(user_id)} ريال"
            )
        except:
            pass

    await message.answer("✅ تم تنفيذ العملية.", reply_markup=admin_keyboard())
    await state.finish()

# ================= حظر مستخدم =================
@dp.message_handler(lambda m: m.text == "🚫 حظر مستخدم")
async def ban_start(message: types.Message):
    if str(message.from_user.id) != ADMIN_ID:
        return
    await message.answer("أرسل آيدي المستخدم للحظر:")
    await BanUser.user_id.set()

@dp.message_handler(state=BanUser.user_id)
async def ban_execute(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("❌ آيدي غير صحيح.")
        return
    user_id = int(message.text)
    database.ban_user(user_id, 1)
    try:
        await bot.send_message(user_id, "🚫 تم حظر حسابك من استخدام البوت.")
    except:
        pass
    await message.answer("🚫 تم الحظر وإرسال إشعار.", reply_markup=admin_keyboard())
    await state.finish()

# ================= فك الحظر =================
@dp.message_handler(lambda m: m.text == "🔓 فك حظر")
async def unban_start(message: types.Message):
    if str(message.from_user.id) != ADMIN_ID:
        return
    await message.answer("أرسل آيدي المستخدم لفك الحظر:")
    await UnbanUser.user_id.set()

@dp.message_handler(state=UnbanUser.user_id)
async def unban_execute(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("❌ آيدي غير صحيح.")
        return
    user_id = int(message.text)
    database.ban_user(user_id, 0)
    try:
        await bot.send_message(
            user_id,
            "🎉 تم فك الحظر عن حسابك.\nالآن يمكنك استخدام البوت بكامل ميزاته الخرافية 😍✔️"
        )
    except:
        pass
    await message.answer("✅ تم فك الحظر وإرسال إشعار.", reply_markup=admin_keyboard())
    await state.finish()

# ================= معلومات مستخدم =================
@dp.message_handler(lambda m: m.text == "👤 معلومات مستخدم")
async def info_user_start(message: types.Message):
    if str(message.from_user.id) != ADMIN_ID:
        return
    await message.answer("أرسل آيدي المستخدم:")
    await InfoUser.user_id.set()

@dp.message_handler(state=InfoUser.user_id)
async def info_user_execute(message: types.Message, state: FSMContext):
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
        reply_markup=admin_keyboard()
    )
    await state.finish()

# ================= إشعار لمستخدم واحد =================
@dp.message_handler(lambda m: m.text == "📢 إشعار لمستخدم")
async def notify_user_start(message: types.Message):
    if str(message.from_user.id) != ADMIN_ID:
        return
    await message.answer("أرسل آيدي المستخدم:")
    await NotifyUser.user_id.set()

@dp.message_handler(state=NotifyUser.user_id)
async def notify_user_get_id(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("❌ آيدي غير صحيح.")
        return
    await state.update_data(user_id=int(message.text))
    await message.answer("أرسل نص الرسالة:")
    await NotifyUser.message.set()

@dp.message_handler(state=NotifyUser.message)
async def notify_user_message(message: types.Message, state: FSMContext):
    await state.update_data(text=message.text)
    await message.answer("هل تريد إرسال الإشعار؟", reply_markup=yes_no_keyboard())
    await NotifyUser.confirm.set()

@dp.message_handler(state=NotifyUser.confirm)
async def notify_user_confirm(message: types.Message, state: FSMContext):
    data = await state.get_data()
    if message.text == "✅ نعم":
        try:
            await bot.send_message(data["user_id"], data["text"])
        except:
            pass
        await message.answer("✅ تم إرسال الإشعار.", reply_markup=admin_keyboard())
    else:
        await message.answer("❌ تم إلغاء الإرسال.", reply_markup=admin_keyboard())
    await state.finish()

# ================= إشعار جماعي =================
@dp.message_handler(lambda m: m.text == "📣 إشعار جماعي")
async def broadcast_start(message: types.Message):
    if str(message.from_user.id) != ADMIN_ID:
        return
    await message.answer("أرسل نص الرسالة الجماعية:")
    await Broadcast.message.set()

@dp.message_handler(state=Broadcast.message)
async def broadcast_message(message: types.Message, state: FSMContext):
    await state.update_data(text=message.text)
    await message.answer("هل تريد إرسال الإشعار لكل المستخدمين النشطين؟", reply_markup=yes_no_keyboard())
    await Broadcast.confirm.set()

@dp.message_handler(state=Broadcast.confirm)
async def broadcast_confirm(message: types.Message, state: FSMContext):
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

# ================= الحسابات منخفضة الرصيد =================
@dp.message_handler(lambda m: m.text == "⚠ الحسابات منخفضة الرصيد")
async def low_balance_users(message: types.Message):
    if str(message.from_user.id) != ADMIN_ID:
        return
    users = database.get_low_balance_users()
    if not users:
        await message.answer("لا يوجد حسابات منخفضة الرصيد.", reply_markup=admin_keyboard())
        return
    text = "⚠ الحسابات منخفضة الرصيد:\n\n"
    for u in users:
        text += f"🆔 {u[0]} | 💰 {u[1]}\n"
    await message.answer(text, reply_markup=admin_keyboard())

# ================= إدارة المناطق =================
@dp.message_handler(lambda m: m.text == "🌍 إدارة المناطق")
async def manage_regions(message: types.Message):
    if str(message.from_user.id) != ADMIN_ID:
        return
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("➕ إضافة منطقة", "🗑 حذف منطقة")
    kb.add("🔙 رجوع")
    await message.answer("إدارة المناطق:", reply_markup=kb)

@dp.message_handler(lambda m: m.text == "➕ إضافة منطقة")
async def add_region_start(message: types.Message):
    if str(message.from_user.id) != ADMIN_ID:
        return
    await message.answer("أرسل اسم المنطقة الجديدة:")
    await AddRegion.name.set()

@dp.message_handler(state=AddRegion.name)
async def add_region_name(message: types.Message, state: FSMContext):
    if message.text == "❌ إلغاء العملية":
        await cancel_operation(message, state)
        return
    name = message.text.strip()
    if name:
        database.add_region(name)
        await message.answer(f"✅ تم إضافة المنطقة '{name}'", reply_markup=admin_keyboard())
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
        await admin_panel(message)
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
        database.delete_region(region_id)
        await message.answer(f"✅ تم حذف المنطقة '{region_name}'", reply_markup=admin_keyboard())
    else:
        await message.answer("❌ المنطقة غير موجودة.")
    await state.finish()

# ================= إدارة المستشفيات =================
@dp.message_handler(lambda m: m.text == "🏥 إدارة المستشفيات")
async def manage_hospitals(message: types.Message):
    if str(message.from_user.id) != ADMIN_ID:
        return
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("➕ إضافة مستشفى", "🗑 حذف مستشفى")
    kb.add("🔙 رجوع")
    await message.answer("إدارة المستشفيات:", reply_markup=kb)

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
        kb.add(f"🌍 {r[1]}")
    kb.add("🔙 رجوع")
    await message.answer("اختر المنطقة:", reply_markup=kb)
    await AddHospital.region.set()

@dp.message_handler(state=AddHospital.region)
async def add_hospital_region(message: types.Message, state: FSMContext):
    if message.text == "🔙 رجوع":
        await admin_panel(message)
        await state.finish()
        return
    region_name = message.text.replace("🌍 ", "")
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
    await message.answer("أرسل اسم المستشفى:")
    await AddHospital.name.set()

@dp.message_handler(state=AddHospital.name)
async def add_hospital_name(message: types.Message, state: FSMContext):
    if message.text == "❌ إلغاء العملية":
        await cancel_operation(message, state)
        return
    name = message.text.strip()
    if name:
        data = await state.get_data()
        database.add_hospital(data["region_id"], name)
        await message.answer(f"✅ تم إضافة المستشفى '{name}'", reply_markup=admin_keyboard())
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
        await admin_panel(message)
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
        database.delete_hospital(hospital_id)
        await message.answer(f"✅ تم حذف المستشفى '{hospital_name}'", reply_markup=admin_keyboard())
    else:
        await message.answer("❌ المستشفى غير موجود.")
    await state.finish()

# ================= إدارة الأقسام =================
@dp.message_handler(lambda m: m.text == "🩺 إدارة الأقسام")
async def manage_departments(message: types.Message):
    if str(message.from_user.id) != ADMIN_ID:
        return
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("➕ إضافة قسم", "🗑 حذف قسم")
    kb.add("🔙 رجوع")
    await message.answer("إدارة الأقسام:", reply_markup=kb)

@dp.message_handler(lambda m: m.text == "➕ إضافة قسم")
async def add_department_start(message: types.Message):
    if str(message.from_user.id) != ADMIN_ID:
        return
    hospitals = database.get_hospitals()
    if not hospitals:
        await message.answer("يجب إضافة مستشفى أولاً.", reply_markup=admin_keyboard())
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
        await admin_panel(message)
        await state.finish()
        return
    hospital_name = message.text.replace("🏥 ", "")
    hospitals = database.get_hospitals()
    hospital_id = None
    for h in hospitals:
        if h[2] == hospital_name:
            hospital_id = h[0]
            break
    if not hospital_id:
        await message.answer("❌ مستشفى غير صحيح.")
        return
    await state.update_data(hospital_id=hospital_id)
    await message.answer("أرسل اسم القسم:")
    await AddDepartment.name.set()

@dp.message_handler(state=AddDepartment.name)
async def add_department_name(message: types.Message, state: FSMContext):
    if message.text == "❌ إلغاء العملية":
        await cancel_operation(message, state)
        return
    name = message.text.strip()
    if name:
        data = await state.get_data()
        database.add_department(data["hospital_id"], name)
        await message.answer(f"✅ تم إضافة القسم '{name}'", reply_markup=admin_keyboard())
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
        await admin_panel(message)
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
        database.delete_department(department_id)
        await message.answer(f"✅ تم حذف القسم '{department_name}'", reply_markup=admin_keyboard())
    else:
        await message.answer("❌ القسم غير موجود.")
    await state.finish()

# ================= إدارة الأطباء =================
@dp.message_handler(lambda m: m.text == "👨‍⚕️ إدارة الأطباء")
async def manage_doctors(message: types.Message):
    if str(message.from_user.id) != ADMIN_ID:
        return
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("➕ إضافة طبيب", "🗑 حذف طبيب")
    kb.add("🔙 رجوع")
    await message.answer("إدارة الأطباء:", reply_markup=kb)

@dp.message_handler(lambda m: m.text == "➕ إضافة طبيب")
async def add_doctor_start(message: types.Message):
    if str(message.from_user.id) != ADMIN_ID:
        return
    departments = database.get_departments()
    if not departments:
        await message.answer("يجب إضافة قسم أولاً.", reply_markup=admin_keyboard())
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
        await admin_panel(message)
        await state.finish()
        return
    department_name = message.text.replace("🩺 ", "")
    departments = database.get_departments()
    department_id = None
    for d in departments:
        if d[2] == department_name:
            department_id = d[0]
            break
    if not department_id:
        await message.answer("❌ قسم غير صحيح.")
        return
    await state.update_data(department_id=department_id)
    await message.answer("أرسل اسم الطبيب:")
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
    await message.answer("أرسل التخصص:")
    await AddDoctor.specialization.set()

@dp.message_handler(state=AddDoctor.specialization)
async def add_doctor_specialization(message: types.Message, state: FSMContext):
    if message.text == "❌ إلغاء العملية":
        await cancel_operation(message, state)
        return
    specialization = message.text.strip()
    if not specialization:
        await message.answer("❌ تخصص غير صالح.")
        return
    await state.update_data(specialization=specialization)
    await message.answer("الرجاء رفع ملف PDF الخاص بالمرضى الذكور:")
    await AddDoctor.pdf_male.set()

@dp.message_handler(content_types=['document'], state=AddDoctor.pdf_male)
async def add_doctor_pdf_male(message: types.Message, state: FSMContext):
    if message.document:
        file_id = message.document.file_id
        await state.update_data(pdf_male=file_id)
        await message.answer("تم استلام ملف الذكور. الآن رفع ملف PDF الخاص بالمرضى الإناث:")
        await AddDoctor.pdf_female.set()
    else:
        await message.answer("❌ يرجى رفع ملف PDF.")

@dp.message_handler(content_types=['document'], state=AddDoctor.pdf_female)
async def add_doctor_pdf_female(message: types.Message, state: FSMContext):
    if message.document:
        file_id = message.document.file_id
        data = await state.get_data()
        database.add_doctor(
            data["department_id"],
            data["name"],
            data["specialization"],
            data["pdf_male"],
            file_id
        )
        await message.answer(f"✅ تم إضافة الطبيب '{data['name']}' بنجاح.", reply_markup=admin_keyboard())
        await state.finish()
    else:
        await message.answer("❌ يرجى رفع ملف PDF.")

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
        await admin_panel(message)
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
        database.delete_doctor(doctor_id)
        await message.answer(f"✅ تم حذف الطبيب '{doctor_name}'", reply_markup=admin_keyboard())
    else:
        await message.answer("❌ الطبيب غير موجود.")
    await state.finish()

# ================= العودة للقائمة الرئيسية =================
@dp.message_handler(lambda m: m.text == "🔙 رجوع", state="*")
async def back_main(message: types.Message, state: FSMContext):
    if await state.get_state() is not None:
        await state.finish()
        await message.answer("❌ تم إلغاء العملية للرجوع.")
    is_admin = str(message.from_user.id) == ADMIN_ID
    await message.answer("القائمة الرئيسية", reply_markup=main_keyboard(is_admin))

if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True)
