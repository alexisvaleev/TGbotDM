import logging
from typing import Optional
from aiogram import types, Dispatcher
from aiogram.types import ReplyKeyboardMarkup
from sqlalchemy.future import select

from database import AsyncSessionLocal
from models import User
from handlers.common           import BACK
from handlers.user_management  import cmd_view_users, start_add_user
from handlers.group_management import start_group_creation, start_group_assignment
from handlers.poll_creation    import start_poll_creation
from handlers.poll_editor      import start_poll_editor
from handlers.poll_management  import start_delete_poll
from handlers.poll_statistics  import start_stats
from handlers.poll_take        import start_take_poll

# Тексты кнопок главного меню
USERS_BTN   = "👥 Пользователи"
POLLS_BTN   = "📝 Опросы"
GROUPS_BTN  = "🏷 Группы"
REPORTS_BTN = "📈 Отчёты"

async def _get_role(tg: int) -> Optional[str]:
    async with AsyncSessionLocal() as s:
        me = (await s.execute(select(User).where(User.tg_id == tg))).scalar_one_or_none()
    return me.role if me else None

async def send_main_menu(message: types.Message):
    role = await _get_role(message.from_user.id)
    kb   = ReplyKeyboardMarkup(resize_keyboard=True)

    if role == "admin":
        kb.add(USERS_BTN, POLLS_BTN).add(GROUPS_BTN, REPORTS_BTN)
    elif role == "teacher":
        kb.add(USERS_BTN, POLLS_BTN).add(GROUPS_BTN, "📋 Пройти опрос")
    else:
        kb.add("📋 Пройти опрос")

    logging.info(f"send_main_menu: role={role}")
    await message.answer("Выберите раздел:", reply_markup=kb)

async def route_menu(message: types.Message):
    txt = message.text.strip()
    logging.info(f"route_menu got: {txt!r}")

    # — главное меню →
    if txt == USERS_BTN:
        kb = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        kb.add("Просмотр пользователей","➕ Добавить пользователя","✏️ Редактировать пользователя").add(BACK)
        return await message.answer("Пользователи:", reply_markup=kb)

    if txt == POLLS_BTN:
        kb = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        kb.add("➕ Создать опрос","✏️ Редактировать опрос").add("🗑 Удалить опрос", BACK)
        return await message.answer("Опросы:", reply_markup=kb)

    if txt == GROUPS_BTN:
        kb = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        kb.add("➕ Создать группу","🔀 Назначить группу").add(BACK)
        return await message.answer("Группы:", reply_markup=kb)

    if txt == REPORTS_BTN:
        kb = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        kb.add("📊 Статистика").add(BACK)
        return await message.answer("Отчёты:", reply_markup=kb)

    # — подменю Пользователи →
    if txt == "Просмотр пользователей":
        return await cmd_view_users(message)
    if txt in ("➕ Добавить пользователя","✏️ Редактировать пользователя"):
        return await start_add_user(message, None)

    # — подменю Группы →
    if txt == "➕ Создать группу":
        return await start_group_creation(message, None)
    if txt == "🔀 Назначить группу":
        return await start_group_assignment(message, None)

    # — подменю Опросы →
    if txt == "➕ Создать опрос":
        return await start_poll_creation(message, None)
    if txt == "✏️ Редактировать опрос":
        return await start_poll_editor(message, None)
    if txt == "🗑 Удалить опрос":
        return await start_delete_poll(message, None)

    # — подменю Отчёты →
    if txt == "📊 Статистика":
        return await start_stats(message, None)

    # — студенты: пройти опрос →
    if txt == "📋 Пройти опрос":
        return await start_take_poll(message, None)

    # назад
    if txt == BACK:
        return await send_main_menu(message)

    # иначе – игнор
    logging.info("route_menu: no match")
    return

def register_menu(dp: Dispatcher):
    dp.register_message_handler(
        route_menu,
        content_types=types.ContentTypes.TEXT,
        state=None
    )

