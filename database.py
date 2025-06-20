# database.py

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# 1) Объявляем Base ДО любых моделей
Base = declarative_base()

from config import load_config
config = load_config()

DATABASE_URL = (
    f"postgresql+asyncpg://"
    f"{config.DB_USER}:{config.DB_PASSWORD}@"
    f"{config.DB_HOST}:{config.DB_PORT}/"
    f"{config.DB_NAME}"
)

# 2) Настраиваем движок и фабрику сессий
engine = create_async_engine(DATABASE_URL, echo=False)
AsyncSessionLocal = sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False
)
async def init_db():
    import models
    async with engine.begin() as conn:
        # Сначала удаляем все таблицы
        await conn.run_sync(Base.metadata.drop_all)
        # А затем создаём заново со всеми колонками
        await conn.run_sync(Base.metadata.create_all)
    print("✅ Все таблицы созданы")
