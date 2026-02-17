import logging
import os
from aiogram import Bot, Dispatcher, executor, types
from aiogram.types import ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup

import database

# ================== إعدادات ==================

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = str(os.getenv("ADMIN_ID")).strip()
REPORT_PRICE = 3

logging.basicConfig(level=logging.INFO)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot, storage=MemoryStorage())

database.init_db()

# ================== Keyboards ==================

def main_keyboard(is_admin=False):
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("💰 رصيدي", "📄 إصدار تقرير")
    if is_admin:
        kb.add("👑 لوحة المطور")
    return kb

def admin_keyboard():
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("➕ إضافة مستشفى")
    kb.add("➕ إضافة قسم")
    kb.add("➕ إضافة طبيب")
    kb.add("🔙 رجوع")
    return kb

# ================== States ==================

class AddHospital(StatesGroup):
    name = State()

class AddDepartment(StatesGroup):
    hospital = State()
    name = State()

class AddDoctor(StatesGroup):
    hospital = State()
    department = State()
    name = State()
    specialty = State()
    license = State()

class ReportFlow(StatesGroup):
    hospital = State()
    department = State()
    doctor = State()

# ================== Start ==================

@dp.message_handler(commands=["start"])
async def start_handler(message: types.Message):
    user_id = message.from_user.id
    username = message.from_user.username or "NoUsername"

    database.init_db()

    is_admin = str(user_id) == ADMIN_ID
    await message.answer(
        "أهلاً بك في نظام التقارير الطبية 👨‍⚕️",
        reply_markup=main_keyboard(is_admin)
    )

# ================== رصيدي ==================

@dp.message_handler(lambda m: m.text == "💰 رصيدي")
async def balance_handler(message: types.Message):
    bal = database.get_balance(message.from_user.id)
    await message.answer(f"رصيدك الحالي: {bal} ريال")

# ================== لوحة المطور ==================

@dp.message_handler(lambda m: m.text == "👑 لوحة المطور")
async def admin_panel(message: types.Message):
    if str(message.from_user.id) != ADMIN_ID:
        return
    await message.answer("لوحة التحكم 👑", reply_markup=admin_keyboard())

# ================== إضافة مستشفى ==================

@dp.message_handler(lambda m: m.text == "➕ إضافة مستشفى")
async def add_hospital_start(message: types.Message):
    if str(message.from_user.id) != ADMIN_ID:
        return
    await message.answer("أرسل اسم المستشفى:")
    await AddHospital.name.set()

@dp.message_handler(state=AddHospital.name)
async def save_hospital(message: types.Message, state: FSMContext):
    database.add_hospital(message.text)
    await message.answer("✅ تم إضافة المستشفى.", reply_markup=admin_keyboard())
    await state.finish()

# ================== إضافة قسم ==================

@dp.message_handler(lambda m: m.text == "➕ إضافة قسم")
async def add_department_start(message: types.Message):
    if str(message.from_user.id) != ADMIN_ID:
        return

    hospitals = database.get_hospitals()
    if not hospitals:
        await message.answer("لا يوجد مستشفيات أولاً.")
        return

    kb = InlineKeyboardMarkup()
    for h in hospitals:
        kb.add(InlineKeyboardButton(h[1], callback_data=f"adddept_{h[0]}"))

    await message.answer("اختر المستشفى:", reply_markup=kb)
    await AddDepartment.hospital.set()

@dp.callback_query_handler(lambda c: c.data.startswith("adddept_"), state=AddDepartment.hospital)
async def choose_hospital_for_dept(callback: types.CallbackQuery, state: FSMContext):
    hospital_id = int(callback.data.split("_")[1])
    await state.update_data(hospital_id=hospital_id)
    await callback.message.answer("أرسل اسم القسم:")
    await AddDepartment.name.set()

@dp.message_handler(state=AddDepartment.name)
async def save_department(message: types.Message, state: FSMContext):
    data = await state.get_data()
    database.add_department(data["hospital_id"], message.text)
    await message.answer("✅ تم إضافة القسم.", reply_markup=admin_keyboard())
    await state.finish()

# ================== إضافة طبيب ==================

@dp.message_handler(lambda m: m.text == "➕ إضافة طبيب")
async def add_doctor_start(message: types.Message):
    if str(message.from_user.id) != ADMIN_ID:
        return

    hospitals = database.get_hospitals()
    kb = InlineKeyboardMarkup()
    for h in hospitals:
        kb.add(InlineKeyboardButton(h[1], callback_data=f"adddoc_{h[0]}"))

    await message.answer("اختر المستشفى:", reply_markup=kb)
    await AddDoctor.hospital.set()

@dp.callback_query_handler(lambda c: c.data.startswith("adddoc_"), state=AddDoctor.hospital)
async def choose_hospital_for_doc(callback: types.CallbackQuery, state: FSMContext):
    hospital_id = int(callback.data.split("_")[1])
    await state.update_data(hospital_id=hospital_id)

    departments = database.get_departments(hospital_id)
    kb = InlineKeyboardMarkup()
    for d in departments:
        kb.add(InlineKeyboardButton(d[2], callback_data=f"docdept_{d[0]}"))

    await callback.message.answer("اختر القسم:", reply_markup=kb)
    await AddDoctor.department.set()

@dp.callback_query_handler(lambda c: c.data.startswith("docdept_"), state=AddDoctor.department)
async def choose_department_for_doc(callback: types.CallbackQuery, state: FSMContext):
    department_id = int(callback.data.split("_")[1])
    await state.update_data(department_id=department_id)
    await callback.message.answer("أرسل اسم الطبيب:")
    await AddDoctor.name.set()

@dp.message_handler(state=AddDoctor.name)
async def doctor_name(message: types.Message, state: FSMContext):
    await state.update_data(name=message.text)
    await message.answer("أرسل التخصص:")
    await AddDoctor.specialty.set()

@dp.message_handler(state=AddDoctor.specialty)
async def doctor_specialty(message: types.Message, state: FSMContext):
    await state.update_data(specialty=message.text)
    await message.answer("أرسل رقم الرخصة:")
    await AddDoctor.license.set()

@dp.message_handler(state=AddDoctor.license)
async def doctor_license(message: types.Message, state: FSMContext):
    data = await state.get_data()
    database.add_doctor(
        data["hospital_id"],
        data["department_id"],
        data["name"],
        data["specialty"],
        message.text
    )
    await message.answer("✅ تم إضافة الطبيب.", reply_markup=admin_keyboard())
    await state.finish()

# ================== إصدار تقرير ==================

@dp.message_handler(lambda m: m.text == "📄 إصدار تقرير")
async def issue_report(message: types.Message):
    bal = database.get_balance(message.from_user.id)
    if bal < REPORT_PRICE:
        await message.answer("❌ رصيدك غير كافي.")
        return

    hospitals = database.get_hospitals()
    kb = InlineKeyboardMarkup()
    for h in hospitals:
        kb.add(InlineKeyboardButton(h[1], callback_data=f"hospital_{h[0]}"))

    await message.answer("اختر المستشفى:", reply_markup=kb)
    await ReportFlow.hospital.set()

@dp.callback_query_handler(lambda c: c.data.startswith("hospital_"), state=ReportFlow.hospital)
async def select_hospital(callback: types.CallbackQuery, state: FSMContext):
    hospital_id = int(callback.data.split("_")[1])
    await state.update_data(hospital_id=hospital_id)

    departments = database.get_departments(hospital_id)
    kb = InlineKeyboardMarkup()
    for d in departments:
        kb.add(InlineKeyboardButton(d[2], callback_data=f"dept_{d[0]}"))

    await callback.message.edit_text("اختر القسم:", reply_markup=kb)
    await ReportFlow.department.set()

@dp.callback_query_handler(lambda c: c.data.startswith("dept_"), state=ReportFlow.department)
async def select_department(callback: types.CallbackQuery, state: FSMContext):
    department_id = int(callback.data.split("_")[1])
    data = await state.get_data()
    hospital_id = data["hospital_id"]

    await state.update_data(department_id=department_id)

    doctors = database.get_doctors(hospital_id, department_id)
    kb = InlineKeyboardMarkup()
    for doc in doctors:
        kb.add(InlineKeyboardButton(doc[3], callback_data=f"doctor_{doc[0]}"))

    await callback.message.edit_text("اختر الطبيب:", reply_markup=kb)
    await ReportFlow.doctor.set()

@dp.callback_query_handler(lambda c: c.data.startswith("doctor_"), state=ReportFlow.doctor)
async def select_doctor(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text("✅ تم اختيار الطبيب.\nسيتم ربطه بمرحلة PDF قريباً.")
    await state.finish()

# ================== تشغيل ==================

if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True)
    kb = InlineKeyboardMarkup()
    for h in hospitals:
        kb.add(InlineKeyboardButton(h[1], callback_data=f"hospital_{h[0]}"))

    await call.message.edit_text("🏥 اختر المستشفى:", reply_markup=kb)

# ---------------- اختيار قسم ----------------

@dp.callback_query_handler(lambda c: c.data.startswith("hospital_"))
async def choose_department(call: types.CallbackQuery):
    hospital_id = int(call.data.split("_")[1])
    departments = database.get_departments(hospital_id)

    if not departments:
        await call.message.edit_text("لا يوجد أقسام حالياً.")
        return

    kb = InlineKeyboardMarkup()
    for d in departments:
        kb.add(InlineKeyboardButton(d[1],
               callback_data=f"department_{hospital_id}_{d[0]}"))

    await call.message.edit_text("🏢 اختر القسم:", reply_markup=kb)

# ---------------- اختيار طبيب ----------------

@dp.callback_query_handler(lambda c: c.data.startswith("department_"))
async def choose_doctor(call: types.CallbackQuery):
    parts = call.data.split("_")
    hospital_id = int(parts[1])
    department_id = int(parts[2])

    doctors = database.get_doctors(hospital_id, department_id)

    if not doctors:
        await call.message.edit_text("لا يوجد أطباء حالياً.")
        return

    kb = InlineKeyboardMarkup()
    for doc in doctors:
        kb.add(InlineKeyboardButton(
            f"{doc[1]} - {doc[2]}",
            callback_data=f"doctor_{doc[0]}"
        ))

    await call.message.edit_text("👨‍⚕️ اختر الطبيب:", reply_markup=kb)

# ---------------- اختيار طبيب نهائي ----------------

@dp.callback_query_handler(lambda c: c.data.startswith("doctor_"))
async def doctor_selected(call: types.CallbackQuery):
    doctor_id = int(call.data.split("_")[1])
    await call.message.edit_text(
        f"✅ تم اختيار الطبيب رقم {doctor_id}\n\n(الخطوة التالية: إدخال بيانات المريض — سنبنيها الآن)"
    )

# ---------------- تشغيل ----------------

if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True)    return kb

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

# ================= Cancel =================

@dp.message_handler(lambda m: m.text == "❌ إلغاء العملية", state="*")
async def cancel_operation(message: types.Message, state: FSMContext):
    if await state.get_state() is None:
        await message.answer("لا توجد عملية لإلغائها.")
        return
    await state.finish()
    await message.answer("✅ تم إلغاء العملية.", reply_markup=admin_keyboard())

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

# ================= Issue Report =================

@dp.message_handler(lambda m: m.text == "📄 إصدار تقرير")
async def issue_report(message: types.Message):
    user = database.get_user(message.from_user.id)
    if user and user[5] == 1:
        await message.answer("🚫 حسابك محظور.")
        return

    balance = database.get_balance(message.from_user.id)
    if balance < 3:
        await message.answer("❌ رصيدك غير كافي.\nالرجاء إعادة الشحن لإصدار تقاريرك بنجاح ✅")
        return

    database.update_balance(message.from_user.id, -3, "report")
    await message.answer("✅ تم خصم 3 ريال.\nسيتم إنشاء التقرير.")
    await check_low_balance(message.from_user.id)

# ================= Admin Panel =================

@dp.message_handler(lambda m: m.text == "👑 لوحة المطور")
async def admin_panel(message: types.Message):
    if str(message.from_user.id) != ADMIN_ID:
        return
    await message.answer("👑 لوحة تحكم المطور", reply_markup=admin_keyboard())

# ================= Add Balance =================

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

# ================= Deduct Balance =================

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

# ================= Ban / Unban =================

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

@dp.message_handler(lambda m: m.text == "🔓 فك حظر")
async def unban_start(message: types.Message):
    if str(message.from_user.id) != ADMIN_ID:
        return
    await message.answer("أرسل آيدي المستخدم لفك الحظر:")
    await BanUser.user_id.set()

@dp.message_handler(state=BanUser.user_id)
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

# ================= User Info =================

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

# ================= Notify Single =================

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

# ================= Broadcast =================

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

# ================= Low Balance List =================

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
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.dispatcher.filters.state import State, StatesGroup

class ReportFlow(StatesGroup):
    hospital = State()
    department = State()
    doctor = State()


# =============== إصدار تقرير ===============

@dp.message_handler(lambda m: m.text == "📄 إصدار تقرير")
async def issue_report_start(message: types.Message):
    hospitals = database.get_hospitals()

    if not hospitals:
        await message.answer("لا يوجد مستشفيات حالياً.")
        return

    kb = InlineKeyboardMarkup()
    for h in hospitals:
        kb.add(InlineKeyboardButton(h[1], callback_data=f"hospital_{h[0]}"))

    await message.answer("اختر المستشفى:", reply_markup=kb)
    await ReportFlow.hospital.set()


@dp.callback_query_handler(lambda c: c.data.startswith("hospital_"), state=ReportFlow.hospital)
async def select_hospital(callback: types.CallbackQuery, state: FSMContext):
    hospital_id = int(callback.data.split("_")[1])
    await state.update_data(hospital_id=hospital_id)

    departments = database.get_departments(hospital_id)

    if not departments:
        await callback.message.edit_text("لا يوجد أقسام لهذا المستشفى.")
        await state.finish()
        return

    kb = InlineKeyboardMarkup()
    for d in departments:
        kb.add(InlineKeyboardButton(d[2], callback_data=f"dept_{d[0]}"))

    await callback.message.edit_text("اختر القسم:", reply_markup=kb)
    await ReportFlow.department.set()


@dp.callback_query_handler(lambda c: c.data.startswith("dept_"), state=ReportFlow.department)
async def select_department(callback: types.CallbackQuery, state: FSMContext):
    department_id = int(callback.data.split("_")[1])
    data = await state.get_data()
    hospital_id = data["hospital_id"]

    await state.update_data(department_id=department_id)

    doctors = database.get_doctors(hospital_id, department_id)

    if not doctors:
        await callback.message.edit_text("لا يوجد أطباء في هذا القسم.")
        await state.finish()
        return

    kb = InlineKeyboardMarkup()
    for doc in doctors:
        kb.add(
            InlineKeyboardButton(
                f"{doc[3]} - {doc[4]}",
                callback_data=f"doctor_{doc[0]}"
            )
        )

    await callback.message.edit_text("اختر الطبيب:", reply_markup=kb)
    await ReportFlow.doctor.set()


@dp.callback_query_handler(lambda c: c.data.startswith("doctor_"), state=ReportFlow.doctor)
async def select_doctor(callback: types.CallbackQuery, state: FSMContext):
    doctor_id = int(callback.data.split("_")[1])
    await state.update_data(doctor_id=doctor_id)

    await callback.message.edit_text("✅ تم اختيار الطبيب.\nسيتم ربطه بنظام التقرير لاحقاً.")
    await state.finish()
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
