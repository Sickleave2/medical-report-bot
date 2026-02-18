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

# ================= Utilities =================

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
    kb.add("👤 معلومات مستخدم")
    kb.add("📢 إشعار لمستخدم", "📣 إشعار جماعي")
    kb.add("⚠ الحسابات منخفضة الرصيد")
    kb.add("🔙 رجوع", "❌ إلغاء العملية")
    return kb

def yes_no_keyboard():
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("✅ نعم", "❌ لا")
    return kb

# ================= STATES =================

class AddBalance(StatesGroup):
    user_id = State()
    amount = State()
    notify = State()

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
    if balance < 3.0:
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

@dp.message_handler(state=CreateReport.choose_hospital)
async def choose_department(message: types.Message, state: FSMContext):
    if message.text == "❌ إلغاء العملية":
        await state.finish()
        await message.answer("تم الإلغاء.", reply_markup=main_keyboard(message.from_user.id))
        return

    hospital_name = message.text.replace("🏥 ", "")
    hospitals = database.get_hospitals()

    hospital_id = None
    for h in hospitals:
        if h[1] == hospital_name:
            hospital_id = h[0]
            break

    if not hospital_id:
        await message.answer("❌ اختيار غير صحيح.")
        return

    await state.update_data(hospital_id=hospital_id, hospital_name=hospital_name)

    departments = database.get_departments(hospital_id)
    if not departments:
        await message.answer("لا توجد أقسام.")
        await state.finish()
        return

    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    for d in departments:
        kb.add(f"🩺 {d[2]}")
    kb.add("❌ إلغاء العملية")

    await message.answer("اختر القسم:", reply_markup=kb)
    await CreateReport.choose_department.set()

@dp.message_handler(state=CreateReport.choose_department)
async def choose_doctor(message: types.Message, state: FSMContext):
    if message.text == "❌ إلغاء العملية":
        await state.finish()
        await message.answer("تم الإلغاء.", reply_markup=main_keyboard(message.from_user.id))
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

    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    for doc in doctors:
        kb.add(f"👨‍⚕️ {doc[3]}")
    kb.add("❌ إلغاء العملية")

    await state.update_data(department_id=department_id)
    await message.answer("اختر الطبيب:", reply_markup=kb)
    await CreateReport.choose_doctor.set()

@dp.message_handler(state=CreateReport.choose_doctor)
async def enter_patient(message: types.Message, state: FSMContext):
    if message.text == "❌ إلغاء العملية":
        await state.finish()
        await message.answer("تم الإلغاء.", reply_markup=main_keyboard(message.from_user.id))
        return

    doctor_name = message.text.replace("👨‍⚕️ ", "")
    await state.update_data(doctor_name=doctor_name)

    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("❌ إلغاء العملية")

    await message.answer("أدخل اسم المريض:", reply_markup=kb)
    await CreateReport.patient_name.set()

@dp.message_handler(state=CreateReport.patient_name)
async def generate_report(message: types.Message, state: FSMContext):
    if message.text == "❌ إلغاء العملية":
        await state.finish()
        await message.answer("تم الإلغاء.", reply_markup=main_keyboard(message.from_user.id))
        return

    data = await state.get_data()
    user_id = message.from_user.id

    database.update_balance(user_id, -3, "report")
    database.save_report(user_id, data["hospital_name"], data["doctor_name"], message.text)

    await message.answer(
        f"✅ تم إنشاء التقرير\n\n"
        f"🏥 {data['hospital_name']}\n"
        f"👨‍⚕️ {data['doctor_name']}\n"
        f"👤 {message.text}",
        reply_markup=main_keyboard(user_id)
    )

    await state.finish()

# ================= ADMIN PANEL =================

@dp.message_handler(lambda m: m.text == "👑 لوحة المطور")
async def admin_panel(message: types.Message):
    if not is_admin(message.from_user.id):
        return
    await message.answer("👑 لوحة تحكم المطور", reply_markup=admin_keyboard())

if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True)
