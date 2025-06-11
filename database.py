# database.py
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

# ЗДЕСЬ — импортируем Base и ВСЕ модели,
# чтобы Base.metadata содержало все таблицы и связи
from models import (
    Base,
    User,
    Group,
    Poll,
    Question,
    Answer,
    UserPollProgress,
    UserAnswer
)

from config import load_config

config = load_config()
DATABASE_URL = (
    f"postgresql+asyncpg://"
    f"{config.DB_USER}:{config.DB_PASSWORD}@"
    f"{config.DB_HOST}:{config.DB_PORT}/"
    f"{config.DB_NAME}"
)

engine = create_async_engine(DATABASE_URL, echo=False)
AsyncSessionLocal = sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False
)

async def init_db(dp):
    """
    Запускает Base.metadata.create_all — теперь в metadata есть и users, и все остальные таблицы.
    """
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("✅ Все таблицы созданы")
