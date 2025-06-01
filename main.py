# main.py
import logging
from aiogram import Bot, Dispatcher, executor, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage

from config import load_config
from handlers import register_handlers
from database import init_db

logging.basicConfig(level=logging.INFO)

config = load_config()

bot = Bot(token=config.BOT_TOKEN)
dp = Dispatcher(bot, storage=MemoryStorage())

register_handlers(dp)

async def on_startup(dispatcher):
    await init_db()
    logging.info("✅ Бот запущен")

if __name__ == '__main__':
    executor.start_polling(dp, skip_updates=True, on_startup=on_startup)
