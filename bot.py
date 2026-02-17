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

# ==============================
# الكيبورد الرئيسي
# ==============================

def main_keyboard(is_admin=False):
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("💰 رصيدي")
    kb.add("📄 إصدار تقرير")
    if is_admin:
        kb.add("👑 لوحة المطور")
    return kb

def admin_keyboard():
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("➕ إضافة رصيد", "➖ خصم رصيد")
    kb.add("🚫 حظر مستخدم", "🔓 فك حظر")
    kb.add("📊 إحصائيات")
    kb.add("🔙 رجوع")
    return kb

# ==============================
# حالات FSM
# ==============================

class AddBalanceState(StatesGroup):
    waiting_for_user_id = State()
    waiting_for_amount = State()

class DeductBalanceState(StatesGroup):
    waiting_for_user_id = State()
    waiting_for_amount = State()

class BanState(StatesGroup):
    waiting_for_user_id = State()

# ==============================
# تسجيل المستخدم
# ==============================

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

# ==============================
# عرض الرصيد
# ==============================

@dp.message_handler(lambda m: m.text == "💰 رصيدي")
async def balance_handler(message: types.Message):
    user = database.get_user(message.from_user.id)
    if user[5] == 1:
        await message.answer("🚫 حسابك محظور.")
        return

    balance = database.get_balance(message.from_user.id)
    await message.answer(f"رصيدك الحالي: {balance} ريال")

# ==============================
# إصدار تقرير
# ==============================

@dp.message_handler(lambda m: m.text == "📄 إصدار تقرير")
async def issue_report(message: types.Message):
    user = database.get_user(message.from_user.id)

    if user[5] == 1:
        await message.answer("🚫 حسابك محظور.")
        return

    balance = database.get_balance(message.from_user.id)

    if balance < 3:
        await message.answer("❌ رصيدك غير كافي.")
        return

    database.update_balance(message.from_user.id, -3, "report")
    await message.answer("✅ تم خصم 3 ريال.\nسيتم إنشاء التقرير.")

# ==============================
# لوحة المطور
# ==============================

@dp.message_handler(lambda m: m.text == "👑 لوحة المطور")
async def admin_panel(message: types.Message):
    if str(message.from_user.id) != ADMIN_ID:
        return
    await message.answer("👑 لوحة تحكم المطور", reply_markup=admin_keyboard())

# ==============================
# إضافة رصيد
# ==============================

@dp.message_handler(lambda m: m.text == "➕ إضافة رصيد")
async def add_balance_start(message: types.Message):
    if str(message.from_user.id) != ADMIN_ID:
        return
    await message.answer("أرسل آيدي المستخدم:")
    await AddBalanceState.waiting_for_user_id.set()

@dp.message_handler(state=AddBalanceState.waiting_for_user_id)
async def add_balance_get_id(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("❌ آيدي غير صحيح، أرسل رقم فقط.")
        return

    await state.update_data(user_id=int(message.text))
    await message.answer("أرسل المبلغ:")
    await AddBalanceState.waiting_for_amount.set()

@dp.message_handler(state=AddBalanceState.waiting_for_amount)
async def add_balance_get_amount(message: types.Message, state: FSMContext):
    try:
        amount = float(message.text)
        if amount <= 0 or amount > 10000:
            raise ValueError
    except:
        await message.answer("❌ مبلغ غير صحيح (من 1 إلى 10000)")
        return

    data = await state.get_data()
    database.update_balance(data['user_id'], amount, "add")

    await message.answer("✅ تم إضافة الرصيد بنجاح", reply_markup=admin_keyboard())
    await state.finish()

# ==============================
# خصم رصيد
# ==============================

@dp.message_handler(lambda m: m.text == "➖ خصم رصيد")
async def deduct_balance_start(message: types.Message):
    if str(message.from_user.id) != ADMIN_ID:
        return
    await message.answer("أرسل آيدي المستخدم:")
    await DeductBalanceState.waiting_for_user_id.set()

@dp.message_handler(state=DeductBalanceState.waiting_for_user_id)
async def deduct_balance_get_id(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("❌ آيدي غير صحيح.")
        return

    await state.update_data(user_id=int(message.text))
    await message.answer("أرسل المبلغ:")
    await DeductBalanceState.waiting_for_amount.set()

@dp.message_handler(state=DeductBalanceState.waiting_for_amount)
async def deduct_balance_get_amount(message: types.Message, state: FSMContext):
    try:
        amount = float(message.text)
        if amount <= 0 or amount > 10000:
            raise ValueError
    except:
        await message.answer("❌ مبلغ غير صحيح.")
        return

    data = await state.get_data()
    database.update_balance(data['user_id'], -amount, "deduct")

    await message.answer("✅ تم خصم الرصيد", reply_markup=admin_keyboard())
    await state.finish()

# ==============================
# حظر / فك حظر
# ==============================

@dp.message_handler(lambda m: m.text == "🚫 حظر مستخدم")
async def ban_user_start(message: types.Message):
    if str(message.from_user.id) != ADMIN_ID:
        return
    await message.answer("أرسل آيدي المستخدم للحظر:")
    await BanState.waiting_for_user_id.set()

@dp.message_handler(state=BanState.waiting_for_user_id)
async def ban_user_execute(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("❌ آيدي غير صحيح.")
        return

    database.ban_user(int(message.text), 1)
    await message.answer("🚫 تم الحظر", reply_markup=admin_keyboard())
    await state.finish()

@dp.message_handler(lambda m: m.text == "🔓 فك حظر")
async def unban_user(message: types.Message):
    if str(message.from_user.id) != ADMIN_ID:
        return
    await message.answer("أرسل آيدي المستخدم لفك الحظر:")
    await BanState.waiting_for_user_id.set()

@dp.message_handler(state=BanState.waiting_for_user_id)
async def unban_user_execute(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("❌ آيدي غير صحيح.")
        return

    database.ban_user(int(message.text), 0)
    await message.answer("✅ تم فك الحظر", reply_markup=admin_keyboard())
    await state.finish()

# ==============================
# رجوع
# ==============================

@dp.message_handler(lambda m: m.text == "🔙 رجوع")
async def back_main(message: types.Message):
    is_admin = str(message.from_user.id) == ADMIN_ID
    await message.answer("رجعنا للقائمة الرئيسية", reply_markup=main_keyboard(is_admin))

if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True)
