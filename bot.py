import logging
import os
from aiogram import Bot, Dispatcher, executor, types
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
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

# ================= Keyboards =================

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

# ================= States =================

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
    patient_data = State()   # لاحقاً سنجمع البيانات يدوياً

# حالات إدارة المناطق
class AddRegion(StatesGroup):
    name = State()

class DeleteRegion(StatesGroup):
    region_id = State()

# حالات إدارة المستشفيات
class AddHospital(StatesGroup):
    region_id = State()
    name = State()

class DeleteHospital(StatesGroup):
    hospital_id = State()

# حالات إدارة الأقسام
class AddDepartment(StatesGroup):
    hospital_id = State()
    name = State()

class DeleteDepartment(StatesGroup):
    department_id = State()

# حالات إدارة الأطباء
class AddDoctor(StatesGroup):
    department_id = State()
    name = State()
    specialization = State()
    pdf_male = State()   # انتظار رفع ملف PDF
    pdf_female = State()

class DeleteDoctor(StatesGroup):
    doctor_id = State()

# ================= Utilities =================

async def check_low_balance(user_id):
    balance = database.get_balance(user_id)
    if balance < 3:
        try:
            await bot.send_message(
                user_id,
                "⚠ رصيدك أوشك على الانتهاء.\nالرجاء إعادة الشحن لإصدار تقاريرك بنجاح ✅"
            )
        except:
            pass

# ================= Cancel (معدل) =================

@dp.message_handler(lambda m: m.text == "❌ إلغاء العملية", state="*")
async def cancel_operation(message: types.Message, state: FSMContext):
    if await state.get_state() is None:
        await message.answer("لا توجد عملية لإلغائها.")
        return
    await state.finish()
    is_admin = str(message.from_user.id) == ADMIN_ID
    await message.answer("✅ تم إلغاء العملية.", reply_markup=admin_keyboard() if is_admin else main_keyboard(False))

# ================= Start =================

@dp.message_handler(commands=['start'])
async def start(message: types.Message):
    user_id = message.from_user.id
    username = message.from_user.username or "NoUsername"
    is_admin = 1 if str(user_id) == ADMIN_ID else 0

    database.add_user(user_id, username, is_admin)

    await message.answer(
        "🩺 أهلاً بك في نظام التقارير الطبية",
        reply_markup=main_keyboard(is_admin)
    )

# ================= Balance =================

@dp.message_handler(lambda m: m.text == "💰 رصيدي")
async def balance_handler(message: types.Message):
    user = database.get_user(message.from_user.id)
    if user and user[5] == 1:
        await message.answer("🚫 حسابك محظور.")
        return
    balance = database.get_balance(message.from_user.id)
    await message.answer(f"رصيدك الحالي: {balance} ريال")

# ================= Issue Report (محدث) =================

@dp.message_handler(lambda m: m.text == "📄 إصدار تقرير")
async def start_report(message: types.Message):
    user = database.get_user(message.from_user.id)
    if user and user[5] == 1:
        await message.answer("🚫 حسابك محظور.")
        return

    balance = database.get_balance(message.from_user.id)
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
    await state.update_data(doctor_id=doctor_id, doctor_name=doctor_name,
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

    # هنا يمكننا طلب بيانات إضافية (الاسم، رقم الملف، الخ) لكن سنبسطها حالياً
    await message.answer("أدخل اسم المريض الكامل:")
    await CreateReport.patient_data.set()

@dp.message_handler(state=CreateReport.patient_data)
async def enter_patient_data(message: types.Message, state: FSMContext):
    if message.text == "❌ إلغاء العملية":
        await cancel_operation(message, state)
        return

    patient_name = message.text
    data = await state.get_data()
    user_id = message.from_user.id

    # خصم الرصيد
    database.update_balance(user_id, -3, "report")

    # حفظ التقرير في قاعدة البيانات
    database.save_report(user_id, data["hospital_name"], data["doctor_name"], patient_name)

    # اختيار قالب PDF حسب الجنس
    pdf_path = data["pdf_male"] if data["gender"] == "ذكر" else data["pdf_female"]

    # TODO: تعبئة PDF باستخدام مكتبة PyMuPDF بعد معرفة أسماء الحقول
    await message.answer(
        f"✅ تم إنشاء التقرير بنجاح (سيتم تفعيل تعبئة PDF لاحقاً)\n\n"
        f"🏥 المستشفى: {data['hospital_name']}\n"
        f"👨‍⚕️ الطبيب: {data['doctor_name']}\n"
        f"👤 المريض: {patient_name}\n"
        f"⚥ الجنس: {data['gender']}\n"
        f"📁 قالب PDF: {pdf_path}",
        reply_markup=main_keyboard(str(user_id) == ADMIN_ID)
    )

    await check_low_balance(user_id)
    await state.finish()

# ================= Admin Panel =================

@dp.message_handler(lambda m: m.text == "👑 لوحة المطور")
async def admin_panel(message: types.Message):
    if str(message.from_user.id) != ADMIN_ID:
        return
    await message.answer("👑 لوحة تحكم المطور", reply_markup=admin_keyboard())

# ================= Region Management =================

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
    await DeleteRegion.region_id.set()

@dp.message_handler(state=DeleteRegion.region_id)
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

# ================= Hospital Management =================

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
    await AddHospital.region_id.set()

@dp.message_handler(state=AddHospital.region_id)
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
    await DeleteHospital.hospital_id.set()

@dp.message_handler(state=DeleteHospital.hospital_id)
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

# ================= Department Management =================

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
    await AddDepartment.hospital_id.set()

@dp.message_handler(state=AddDepartment.hospital_id)
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
    await DeleteDepartment.department_id.set()

@dp.message_handler(state=DeleteDepartment.department_id)
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

# ================= Doctor Management =================

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
    await AddDoctor.department_id.set()

@dp.message_handler(state=AddDoctor.department_id)
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
    await message.answer("أرسل ملف PDF الخاص بالمرضى الذكور (ارفع الملف الآن):")
    await AddDoctor.pdf_male.set()

@dp.message_handler(content_types=['document'], state=AddDoctor.pdf_male)
async def add_doctor_pdf_male(message: types.Message, state: FSMContext):
    if message.document:
        file_id = message.document.file_id
        # يمكننا حفظ file_id أو تحميل الملف وحفظ المسار
        # سنقوم بحفظ file_id مؤقتاً
        await state.update_data(pdf_male=file_id)
        await message.answer("تم استلام ملف الذكور. أرسل ملف PDF الخاص بالمرضى الإناث:")
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
    await DeleteDoctor.doctor_id.set()

@dp.message_handler(state=DeleteDoctor.doctor_id)
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

# ================= باقي وظائف الأدمن (كما هي) =================
# (إضافة رصيد، خصم، حظر، معلومات، إشعارات، ...)

# ================= Back =================

@dp.message_handler(lambda m: m.text == "🔙 رجوع", state="*")
async def back_main(message: types.Message, state: FSMContext):
    if await state.get_state() is not None:
        await state.finish()
        await message.answer("❌ تم إلغاء العملية للرجوع.")
    is_admin = str(message.from_user.id) == ADMIN_ID
    await message.answer("القائمة الرئيسية", reply_markup=main_keyboard(is_admin))

if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True)
