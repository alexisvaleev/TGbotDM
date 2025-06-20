from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from config import load_config

cfg = load_config()
Base = declarative_base()

DATABASE_URL = (
    f"postgresql+asyncpg://"
    f"{cfg.DB_USER}:{cfg.DB_PASSWORD}"
    f"@{cfg.DB_HOST}:{cfg.DB_PORT}/{cfg.DB_NAME}"
)

engine = create_async_engine(DATABASE_URL, echo=False)
AsyncSessionLocal = sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False
)

async def init_db():
    # регистрируем все таблицы
    import models
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("✅ Все таблицы созданы (или уже были)")
