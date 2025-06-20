import logging
from typing import Optional
from aiogram import types, Dispatcher
from aiogram.types import ReplyKeyboardMarkup
from sqlalchemy.future import select

from database import AsyncSessionLocal
from models import User
from .common           import BACK
from .user_management  import cmd_view_users, start_add_user, start_delete_user
from .group_management import start_group_creation, start_group_assignment
from .poll_creation    import start_poll_creation
from .poll_editor      import start_poll_editor
from .poll_management  import start_delete_poll
from .poll_statistics  import start_stats
from .poll_take        import start_take_poll

# Главные кнопки
USERS_BTN   = "👥 Пользователи"
POLLS_BTN   = "📝 Опросы"
GROUPS_BTN  = "🏷 Группы"
STATISTICS_BTN = "📊 Статистика"


async def _get_role(tg_id: int) -> Optional[str]:
    async with AsyncSessionLocal() as s:
        me = (await s.execute(
            select(User).where(User.tg_id == tg_id)
        )).scalar_one_or_none()
    return me.role if me else None

async def send_main_menu(message: types.Message):
    role = await _get_role(message.from_user.id)
    kb   = ReplyKeyboardMarkup(resize_keyboard=True)
    if role == "admin":
        kb.add(USERS_BTN, POLLS_BTN).add(GROUPS_BTN, STATISTICS_BTN)
    elif role == "teacher":
        kb.add(USERS_BTN, POLLS_BTN).add(GROUPS_BTN, STATISTICS_BTN)
        kb.add("📋 Пройти опрос")
    else:
        kb.add("📋 Пройти опрос")
    logging.info(f"send_main_menu: role={role}")
    await message.answer("Выберите раздел:", reply_markup=kb)

async def route_menu(message: types.Message):
    txt = message.text.strip()
    logging.info(f"route_menu got: {txt!r}")

    # Пользователи
    if txt == USERS_BTN:
        kb = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        kb.add("Просмотр пользователей",
               "➕ Добавить пользователя",
               "✏️ Редактировать пользователя", "🗑 Удалить пользователя")\
          .add(BACK)
        return await message.answer("Пользователи:", reply_markup=kb)

    # Опросы
    if txt == POLLS_BTN:
        kb = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        kb.add("➕ Создать опрос","✏️ Редактировать опрос")\
          .add("🗑 Удалить опрос", BACK)
        return await message.answer("Опросы:", reply_markup=kb)

    # Группы
    if txt == GROUPS_BTN:
        kb = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        kb.add("➕ Создать группу","🔀 Назначить группу")\
          .add(BACK)
        return await message.answer("Группы:", reply_markup=kb)

    # Отчёты
    if txt == STATISTICS_BTN:
        return await start_stats(message, None)

    # Подменю – Пользователи
    if txt == "Просмотр пользователей":
        return await cmd_view_users(message)
    if txt in ("➕ Добавить пользователя","✏️ Редактировать пользователя"):
        return await start_add_user(message, None)
    if txt == "🗑 Удалить пользователя":
        return await start_delete_user(message, None)

    # Подменю – Группы
    if txt == "➕ Создать группу":
        return await start_group_creation(message, None)
    if txt == "🔀 Назначить группу":
        return await start_group_assignment(message, None)

    # Подменю – Создание опроса
    if txt == "➕ Создать опрос":
        return await start_poll_creation(message, None)
    if txt == "✏️ Редактировать опрос":
        return await start_poll_editor(message, None)
    if txt == "🗑 Удалить опрос":
        return await start_delete_poll(message, None)

    # Подменю – Статистика
    if txt == "📊 Статистика":
        return await start_stats(message, None)

    # Студенты – Пройти опрос
    if txt == "📋 Пройти опрос":
        return await start_take_poll(message, None)

    # Назад
    if txt == BACK:
        return await send_main_menu(message)

    logging.info("route_menu: no match")
    return

def register_menu(dp: Dispatcher):
    dp.register_message_handler(
        route_menu,
        content_types=types.ContentTypes.TEXT,
        state=None   # только когда нет активного FSM
    )
