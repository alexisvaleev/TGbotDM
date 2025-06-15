import logging
from aiogram import Bot, Dispatcher, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.utils import executor
from sqlalchemy.future import select

from config import load_config
from database import init_db, AsyncSessionLocal
from models import Group
from handlers import register_handlers
from handlers.user_management import add_users_to_db

# Конфиг и бот
config = load_config()
bot = Bot(token=config.BOT_TOKEN, parse_mode=types.ParseMode.HTML)
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)

# Регистрируем все хендлеры
register_handlers(dp)
logging.info("🔌 Handlers registered")


async def seed_groups():
    """Сеем группы из .env (GROUP_NAMES) при старте."""
    if not config.GROUP_NAMES:
        return

    async with AsyncSessionLocal() as session:
        existing = {g.name for g in (await session.execute(select(Group))).scalars().all()}
        for name in config.GROUP_NAMES:
            if name not in existing:
                session.add(Group(name=name))
        await session.commit()
    logging.info("✅ Groups seeded")


async def on_startup(dp: Dispatcher):
    await init_db(dp)          # создаём таблицы
    await seed_groups()        # грузим группы из .env
    await add_users_to_db(dp)  # авто-добавляем пользователей из .env
    logging.info("✅ on_startup completed")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    executor.start_polling(
        dp,
        skip_updates=False,  # при отладке лучше не пропускать апдейты
        on_startup=on_startup,
    )
