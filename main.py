import logging
from aiogram import Bot, Dispatcher, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.utils import executor

from config import load_config
from database import init_db
from handlers import register_handlers

logging.basicConfig(level=logging.INFO)
config = load_config()

bot = Bot(token=config.BOT_TOKEN, parse_mode=types.ParseMode.HTML)
dp  = Dispatcher(bot, storage=MemoryStorage())

# Регистрируем ВСЕ модули одним вызовом
register_handlers(dp)

async def on_startup(_):
    # Создаём таблицы (без drop_all!)
    await init_db()
    logging.info("✅ init_db done")

if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=False, on_startup=on_startup)
