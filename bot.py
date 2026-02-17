import logging
import os
from aiogram import Bot, Dispatcher, executor, types

BOT_TOKEN = os.getenv("BOT_TOKEN")

logging.basicConfig(level=logging.INFO)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)


@dp.message_handler(commands=['start'])
async def start(message: types.Message):
    await message.answer("🩺 البوت يعمل بنجاح على Railway 🚀")


if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True)
