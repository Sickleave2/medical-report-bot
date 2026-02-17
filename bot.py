import logging
import os
from aiogram import Bot, Dispatcher, executor, types
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
import database

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = os.getenv("ADMIN_ID")

logging.basicConfig(level=logging.INFO)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)

database.init_db()

# --------------------------
# إنشاء الكيبورد
# --------------------------

def main_keyboard(is_admin=False):
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(KeyboardButton("💰 رصيدي"))
    kb.add(KeyboardButton("📄 إصدار تقرير"))

    if is_admin:
        kb.add(KeyboardButton("👑 لوحة المطور"))

    return kb


# --------------------------
# تسجيل المستخدم
# --------------------------

@dp.message_handler(commands=['start'])
async def start(message: types.Message):
    user_id = message.from_user.id
    username = message.from_user.username or "NoUsername"

    is_admin = 1 if str(user_id) == str(ADMIN_ID) else 0

    database.add_user(user_id, username, is_admin)

    await message.answer(
        "🩺 تم تسجيلك في النظام بنجاح!",
        reply_markup=main_keyboard(is_admin)
    )


# --------------------------
# عرض الرصيد
# --------------------------

@dp.message_handler(lambda m: m.text == "💰 رصيدي")
async def balance_handler(message: types.Message):
    user = database.get_user(message.from_user.id)

    if not user:
        return

    if user[5] == 1:
        await message.answer("🚫 حسابك محظور.")
        return

    balance = database.get_balance(message.from_user.id)
    await message.answer(f"رصيدك الحالي: {balance} ريال")


# --------------------------
# إصدار تقرير (تجريبي حالياً)
# --------------------------

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

    await message.answer("✅ تم خصم 3 ريال.\nسيتم إنشاء التقرير قريباً.")


# --------------------------
# لوحة المطور
# --------------------------

@dp.message_handler(lambda m: m.text == "👑 لوحة المطور")
async def admin_panel(message: types.Message):
    if str(message.from_user.id) != str(ADMIN_ID):
        return

    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(KeyboardButton("➕ إضافة رصيد"))
    kb.add(KeyboardButton("🚫 حظر مستخدم"))
    kb.add(KeyboardButton("🔓 فك حظر مستخدم"))
    kb.add(KeyboardButton("🔙 رجوع"))

    await message.answer("👑 لوحة تحكم المطور", reply_markup=kb)


# --------------------------
# رجوع للقائمة
# --------------------------

@dp.message_handler(lambda m: m.text == "🔙 رجوع")
async def back_main(message: types.Message):
    is_admin = str(message.from_user.id) == str(ADMIN_ID)
    await message.answer("تم الرجوع للقائمة الرئيسية", reply_markup=main_keyboard(is_admin))


if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True)
