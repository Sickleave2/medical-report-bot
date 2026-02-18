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
