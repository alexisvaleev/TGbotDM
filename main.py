from aiogram import Bot, Dispatcher, types
from aiogram.utils import executor
from config import load_config
from handlers import register_handlers
from aiogram.contrib.fsm_storage.memory import MemoryStorage

# Включаем логирование
import logging
logging.basicConfig(level=logging.INFO)

config = load_config()

bot = Bot(token=config.BOT_TOKEN)
dp = Dispatcher(bot, storage=MemoryStorage())

register_handlers(dp)

if __name__ == '__main__':
    executor.start_polling(dp, skip_updates=True)
