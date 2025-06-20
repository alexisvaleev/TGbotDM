import logging
from aiogram import Bot, Dispatcher, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.utils import executor

from config import load_config
from database import init_db
from handlers import register_handlers

# сидеры
from handlers.user_management import add_users_to_db
from handlers.group_management import seed_groups

logging.basicConfig(level=logging.INFO)
config = load_config()

bot = Bot(token=config.BOT_TOKEN, parse_mode=types.ParseMode.HTML)
dp  = Dispatcher(bot, storage=MemoryStorage())

# Регистрируем все хендлеры
register_handlers(dp)

async def on_startup(_):
    # создаем таблицы (без drop)
    await init_db()
    # seed-группы и seed-пользователей
    await seed_groups()
    await add_users_to_db()
    logging.info("✅ on_startup completed")

if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=False, on_startup=on_startup)
