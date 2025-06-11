# main.py
import asyncio
from aiogram import Bot, Dispatcher
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.utils import executor

from config import load_config
from database import init_db
from handlers import register_handlers
from handlers.start import add_users_to_db

config = load_config()
bot = Bot(token=config.BOT_TOKEN)

# Подключаем хранилище для FSM
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)

# Регистрируем все ваши хендлеры
register_handlers(dp)

async def on_startup(dp: Dispatcher):
    # 1) создаём таблицы в БД
    await init_db(dp)
    # 2) добавляем админов/учителей/студентов
    await add_users_to_db(dp)

if __name__ == "__main__":
    executor.start_polling(
        dp,
        skip_updates=True,
        on_startup=on_startup,
    )
