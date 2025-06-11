from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from config import load_config
from models import Base

config = load_config()

DATABASE_URL = (
    f"postgresql+asyncpg://"
    f"{config.DB_USER}:"
    f"{config.DB_PASSWORD}@"
    f"{config.DB_HOST}:"
    f"{config.DB_PORT}/"
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
    Создаёт все таблицы, описанные в models.Base.
    Удалён лишний `await conn`, чтобы не было InvalidRequestError.
    """
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("✅ База данных инициализирована")
