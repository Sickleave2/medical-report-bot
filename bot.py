import logging
import os
from aiogram import Bot, Dispatcher, executor, types
from aiogram.types import ReplyKeyboardMarkup
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

# ================= UTILITIES =================

def is_admin(user_id):
    return str(user_id) == ADMIN_ID

def main_keyboard(user_id):
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("💰 رصيدي", "📄 إصدار تقرير")
    if is_admin(user_id):
        kb.add("👑 لوحة المطور")
    return kb

def admin_keyboard():
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("➕ إضافة رصيد", "➖ خصم رصيد")
    kb.add("🚫 حظر مستخدم", "🔓 فك حظر")
    kb.add("🔙 رجوع")
    return kb

# ================= STATES =================

class CreateReport(StatesGroup):
    choose_hospital = State()
    choose_department = State()
    choose_doctor = State()
    patient_name = State()

# ================= START =================

@dp.message_handler(commands=['start'])
async def start(message: types.Message):
    user_id = message.from_user.id
    username = message.from_user.username or "NoUsername"

    database.add_user(user_id, username, 1 if is_admin(user_id) else 0)

    await message.answer(
        "🩺 أهلاً بك في نظام التقارير الطبية",
        reply_markup=main_keyboard(user_id)
    )

# ================= CANCEL =================

@dp.message_handler(lambda m: m.text == "❌ إلغاء العملية", state="*")
async def cancel(message: types.Message, state: FSMContext):
    if await state.get_state() is None:
        await message.answer("لا توجد عملية لإلغائها.")
        return

    await state.finish()
    await message.answer(
        "✅ تم إلغاء العملية.",
        reply_markup=main_keyboard(message.from_user.id)
    )

# ================= BALANCE =================

@dp.message_handler(lambda m: m.text == "💰 رصيدي")
async def balance(message: types.Message):
    user = database.get_user(message.from_user.id)
    if user and user[5] == 1:
        await message.answer("🚫 حسابك محظور.")
        return

    balance = float(database.get_balance(message.from_user.id))
    await message.answer(f"رصيدك الحالي: {balance} ريال")

# ================= ISSUE REPORT =================

@dp.message_handler(lambda m: m.text == "📄 إصدار تقرير")
async def start_report(message: types.Message):
    user = database.get_user(message.from_user.id)

    if user and user[5] == 1:
        await message.answer("🚫 حسابك محظور.")
        return

    balance = float(database.get_balance(message.from_user.id))
    if balance < 3:
        await message.answer("❌ رصيدك غير كافي.")
        return

    hospitals = database.get_hospitals()
    if not hospitals:
        await message.answer("لا توجد مستشفيات مسجلة.")
        return

    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    for h in hospitals:
        kb.add(f"🏥 {h[1]}")
    kb.add("❌ إلغاء العملية")

    await message.answer("اختر المستشفى:", reply_markup=kb)
    await CreateReport.choose_hospital.set()

# ================= STEP 1 =================

@dp.message_handler(state=CreateReport.choose_hospital)
async def choose_department(message: types.Message, state: FSMContext):

    hospital_name = message.text.replace("🏥 ", "")
    hospitals = database.get_hospitals()

    hospital = next((h for h in hospitals if h[1] == hospital_name), None)

    if not hospital:
        await message.answer("❌ اختر مستشفى من القائمة فقط.")
        return

    await state.update_data(
        hospital_id=hospital[0],
        hospital_name=hospital[1]
    )

    departments = database.get_departments(hospital[0])

    if not departments:
        await message.answer("لا توجد أقسام في هذا المستشفى.")
        await state.finish()
        return

    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    for d in departments:
        kb.add(f"🩺 {d[2]}")
    kb.add("❌ إلغاء العملية")

    await message.answer("اختر القسم:", reply_markup=kb)
    await CreateReport.choose_department.set()

# ================= STEP 2 =================

@dp.message_handler(state=CreateReport.choose_department)
async def choose_doctor(message: types.Message, state: FSMContext):

    department_name = message.text.replace("🩺 ", "")
    data = await state.get_data()

    departments = database.get_departments(data["hospital_id"])
    department = next((d for d in departments if d[2] == department_name), None)

    if not department:
        await message.answer("❌ اختر قسم من القائمة فقط.")
        return

    await state.update_data(department_id=department[0])

    doctors = database.get_doctors(department[0])

    if not doctors:
        await message.answer("لا يوجد أطباء في هذا القسم.")
        await state.finish()
        return

    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    for doc in doctors:
        kb.add(f"👨‍⚕️ {doc[3]}")
    kb.add("❌ إلغاء العملية")

    await message.answer("اختر الطبيب:", reply_markup=kb)
    await CreateReport.choose_doctor.set()

# ================= STEP 3 =================

@dp.message_handler(state=CreateReport.choose_doctor)
async def enter_patient(message: types.Message, state: FSMContext):

    doctor_name = message.text.replace("👨‍⚕️ ", "")
    data = await state.get_data()

    doctors = database.get_doctors(data["department_id"])
    doctor = next((d for d in doctors if d[3] == doctor_name), None)

    if not doctor:
        await message.answer("❌ اختر طبيب من القائمة فقط.")
        return

    await state.update_data(doctor_name=doctor[3])

    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("❌ إلغاء العملية")

    await message.answer("أدخل اسم المريض:", reply_markup=kb)
    await CreateReport.patient_name.set()

# ================= FINAL STEP =================

@dp.message_handler(state=CreateReport.patient_name)
async def generate_report(message: types.Message, state: FSMContext):

    patient_name = message.text.strip()

    if len(patient_name) < 3:
        await message.answer("❌ اسم غير صحيح.")
        return

    data = await state.get_data()
    user_id = message.from_user.id

    # خصم الرصيد
    database.update_balance(user_id, -3, "report")

    # حفظ التقرير
    database.save_report(
        user_id,
        data["hospital_name"],
        data["doctor_name"],
        patient_name
    )

    await message.answer(
        f"✅ تم إنشاء التقرير بنجاح\n\n"
        f"🏥 {data['hospital_name']}\n"
        f"👨‍⚕️ {data['doctor_name']}\n"
        f"👤 {patient_name}",
        reply_markup=main_keyboard(user_id)
    )

    await state.finish()

# ================= ADMIN PANEL =================

@dp.message_handler(lambda m: m.text == "👑 لوحة المطور")
async def admin_panel(message: types.Message):
    if not is_admin(message.from_user.id):
        return
    await message.answer("👑 لوحة تحكم المطور", reply_markup=admin_keyboard())

# ================= BACK =================

@dp.message_handler(lambda m: m.text == "🔙 رجوع")
async def back(message: types.Message):
    await message.answer("القائمة الرئيسية", reply_markup=main_keyboard(message.from_user.id))

# ================= RUN =================

if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True)
