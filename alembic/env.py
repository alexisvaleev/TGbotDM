from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from alembic import context
from models import Base
from dotenv import load_dotenv
import os

# Загружаем переменные из .env
load_dotenv()

# Получаем значения из .env
DB_USER = os.getenv('DB_USER')
DB_PASSWORD = os.getenv('DB_PASSWORD')
DB_HOST = os.getenv('DB_HOST')
DB_PORT = os.getenv('DB_PORT')
DB_NAME = os.getenv('DB_NAME')

# Строка подключения
DATABASE_URL = f"postgresql+asyncpg://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

# Настроим асинхронное подключение
engine = create_async_engine(DATABASE_URL, echo=True)

# Создайте сессию
SessionLocal = sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False
)

# Настройка метаданных
target_metadata = Base.metadata

def run_migrations_online():
    # Получаем параметры конфигурации
    connectable = engine
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )
        with context.begin_transaction():
            context.run_migrations()

if __name__ == "__main__":
    run_migrations_online()
