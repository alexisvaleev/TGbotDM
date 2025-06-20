# handlers/user_management.py

import itertools
from aiogram import types, Dispatcher
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import StatesGroup, State
from aiogram.types import ReplyKeyboardRemove, ReplyKeyboardMarkup, KeyboardButton
from sqlalchemy.future import select
from sqlalchemy import insert

from config import load_config
from database import AsyncSessionLocal
from models import User, Group
from handlers.common import BACK, BACK_BTN
from handlers.back import return_to_main_menu

config = load_config()

class UserMgmtStates(StatesGroup):
    waiting_for_id   = State()
    waiting_for_role = State()


async def add_users_to_db(dp: Dispatcher):
    """
    Синхронизирует пользователей из .env (ADMIN_IDS, TEACHER_IDS, STUDENT_IDS)
    в таблице users: добавляет, если ещё нет.
    """
    ids_roles = (
        (config.ADMIN_IDS,   "admin"),
        (config.TEACHER_IDS, "teacher"),
        (config.STUDENT_IDS, "student"),
    )
    async with AsyncSessionLocal() as session:
        for ids, role in ids_roles:
            for tg_id in ids:
                row = await session.execute(
                    select(User).where(User.tg_id == tg_id)
                )
                if not row.scalar_one_or_none():
                    session.add(User(tg_id=tg_id, role=role))
        await session.commit()
    print("✅ add_users_to_db: users synced from .env")


async def cmd_view_users(message: types.Message):
    """
    Показывает список всех пользователей с ФИО, ролью и группой.
    Доступно admin и teacher.
    """
    tg = message.from_user.id
    async with AsyncSessionLocal() as session:
        me = (await session.execute(
            select(User).where(User.tg_id == tg)
        )).scalar_one_or_none()
        if not me or me.role not in ("admin", "teacher"):
            return await message.answer("⛔ У вас нет прав.")

        users = (await session.execute(select(User))).scalars().all()
        groups = (await session.execute(select(Group))).scalars().all()
    grp_map = {g.id: g.name for g in groups}

    lines = []
    for u in users:
        fio = " ".join(filter(None, (
            getattr(u, "surname", "") or "",
            getattr(u, "name",      "") or "",
            getattr(u, "patronymic","") or "",
        ))).strip() or "—"
        grp_name = grp_map.get(u.group_id, "—")
        lines.append(f"{u.id}. {fio} ({u.role}) — {grp_name}")

    text = "\n".join(lines) or "🚫 Нет пользователей."
    await message.answer(text, reply_markup=BACK_BTN)


async def start_add_user(message: types.Message, state: FSMContext):
    """
    Начинает FSM для ввода нового Telegram ID пользователя.
    Доступно admin и teacher.
    """
    tg = message.from_user.id
    async with AsyncSessionLocal() as session:
        me = (await session.execute(
            select(User).where(User.tg_id == tg)
        )).scalar_one_or_none()
    if not me or me.role not in ("admin", "teacher"):
        return await message.answer("⛔ У вас нет прав.")

    await UserMgmtStates.waiting_for_id.set()
    await message.answer(
        "Введите Telegram ID пользователя для добавления/обновления:",
        reply_markup=ReplyKeyboardRemove()
    )


async def process_user_id(message: types.Message, state: FSMContext):
    """
    Получает Telegram ID, сохраняет и предлагает выбрать роль.
    """
    txt = message.text.strip()
    if txt == BACK:
        await state.finish()
        return await return_to_main_menu(message)
    if not txt.isdigit():
        return await message.answer("⛔ Пожалуйста, введите числовой ID.")

    await state.update_data(new_tg_id=int(txt))

    kb = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    for role in ("admin", "teacher", "student"):
        kb.add(KeyboardButton(role))
    kb.add(BACK_BTN)

    await UserMgmtStates.waiting_for_role.set()
    await message.answer("Выберите роль для этого пользователя:", reply_markup=kb)


async def process_user_role(message: types.Message, state: FSMContext):
    """
    Получает роль и создаёт или обновляет пользователя в БД.
    """
    txt = message.text.strip().lower()
    if txt == BACK:
        await state.finish()
        return await return_to_main_menu(message)
    if txt not in ("admin", "teacher", "student"):
        return await message.answer("⛔ Пожалуйста, выберите роль кнопками.")

    data = await state.get_data()
    new_tg = data["new_tg_id"]

    async with AsyncSessionLocal() as session:
        existing = (await session.execute(
            select(User).where(User.tg_id == new_tg)
        )).scalar_one_or_none()

        if existing:
            # Обновляем роль
            await session.execute(
                User.__table__.update()
                .where(User.tg_id == new_tg)
                .values(role=txt)
            )
            msg = f"✅ Роль пользователя {new_tg} обновлена на «{txt}»."
        else:
            # Создаём нового
            await session.execute(
                insert(User).values(
                    tg_id=new_tg,
                    role=txt,
                    group_id=None,
                    surname=None,
                    name=None,
                    patronymic=None
                )
            )
            msg = f"✅ Пользователь {new_tg} добавлен с ролью «{txt}»."

        await session.commit()

    await state.finish()
    await message.answer(msg, reply_markup=ReplyKeyboardRemove())
    return await return_to_main_menu(message)


def register_user_management(dp: Dispatcher):
    # Синхронизировать пользователей из .env при запуске
    # вызывается из main.py: await add_users_to_db(dp)
    # -----------------------------
    dp.register_message_handler(
        cmd_view_users,
        text=["👥 Просмотр пользователей", "👥 Управление пользователями"],
        state="*"
    )
    dp.register_message_handler(
        start_add_user,
        text="➕ Добавить пользователя",
        state="*"
    )
    dp.register_message_handler(
        process_user_id,
        state=UserMgmtStates.waiting_for_id
    )
    dp.register_message_handler(
        process_user_role,
        state=UserMgmtStates.waiting_for_role
    )
