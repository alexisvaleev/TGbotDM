import os
import sys
from logging.config import fileConfig
from models import Base, User, Group, Poll, Question, Answer, UserPollProgress, UserAnswer
target_metadata = Base.metadata

from alembic import context
from sqlalchemy import engine_from_config, pool, create_engine
from dotenv import load_dotenv

# ------------------------------------------------------------------------------
#                      1) Подготовка PYTHONPATH и .env
# ------------------------------------------------------------------------------

# Поднимаем корень проекта (тот, где лежат main.py, models.py и т.д.)
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, PROJECT_ROOT)

# Загружаем переменные окружения из .env
load_dotenv(os.path.join(PROJECT_ROOT, ".env"))

# ------------------------------------------------------------------------------
#              2) Импортируем Base и ВСЕ модели (чтобы metadata был полный)
# ------------------------------------------------------------------------------
from models import (
    Base,
    User,
    Group,
    Poll,
    Question,
    Answer,
    UserPollProgress,
    UserAnswer,
)

# ------------------------------------------------------------------------------
#                3) Настройка Alembic и переопределение URL
# ------------------------------------------------------------------------------
config = context.config

# Если в alembic.ini прописан любой sqlalchemy.url – мы его полностью заменяем:
DB_USER     = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_HOST     = os.getenv("DB_HOST")
DB_PORT     = os.getenv("DB_PORT")
DB_NAME     = os.getenv("DB_NAME")

SYNC_DATABASE_URL = (
    f"postgresql+psycopg2://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
)
config.set_main_option("sqlalchemy.url", SYNC_DATABASE_URL)

# Логирование из alembic.ini
fileConfig(config.config_file_name)

# Указываем Alembic, по каким метаданным генерить
target_metadata = Base.metadata


# ------------------------------------------------------------------------------
#                       4) Функции offline/online режимов
# ------------------------------------------------------------------------------
def run_migrations_offline():
    """Generate SQL scripts without DB-connection."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    """Run migrations against a live database."""
    # создаём синхронный Engine на базе psycopg2-URL
    connectable = create_engine(
        config.get_main_option("sqlalchemy.url"),
        poolclass=pool.NullPool,
        echo=False,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            # при необходимости: compare_type=True, include_schemas=True и пр.
        )
        with context.begin_transaction():
            context.run_migrations()


# ------------------------------------------------------------------------------
#                      5) Выбор режима и запуск
# ------------------------------------------------------------------------------
if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
