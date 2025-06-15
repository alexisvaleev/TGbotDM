# handlers/start.py

from aiogram import types, Dispatcher
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import StatesGroup, State
from aiogram.types import (
    ReplyKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardRemove
)
from sqlalchemy.future import select

from config import load_config
from database import AsyncSessionLocal
from models import User, Group

# грузим .env
config = load_config()

class SettingGroup(StatesGroup):
    waiting_for_group = State()


async def cmd_start(message: types.Message, state: FSMContext):
    """
    /start — регистрируем пользователя (если нужно), спрашиваем группу или рисуем меню.
    """
    # отменяем любой активный FSM
    await state.finish()
    tg_id = message.from_user.id

    # 1) проверяем, есть ли в БД
    async with AsyncSessionLocal() as session:
        user = (await session.execute(
            select(User).where(User.tg_id == tg_id)
        )).scalar_one_or_none()

        if not user:
            # роль из .env
            if tg_id in config.ADMIN_IDS:
                role = "admin"
            elif tg_id in config.TEACHER_IDS:
                role = "teacher"
            elif tg_id in config.STUDENT_IDS:
                role = "student"
            else:
                role = "unknown"

            user = User(tg_id=tg_id, role=role)
            session.add(user)
            await session.commit()

    # 2) если преподаватель или студент без группы — спрашиваем группу
    if user.role in ("teacher", "student") and not user.group_id:
        # берём все группы из БД
        async with AsyncSessionLocal() as session:
            groups = (await session.execute(select(Group))).scalars().all()

        kb = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        for g in groups:
            kb.add(KeyboardButton(g.name))

        await SettingGroup.waiting_for_group.set()
        return await message.answer(
            "Пожалуйста, выберите вашу группу:",
            reply_markup=kb
        )

    # 3) иначе сразу показываем меню
    return await _send_main_menu(message, user.role)


async def process_group_choice(message: types.Message, state: FSMContext):
    """
    Сохраняем выбранную группу и рисуем меню.
    """
    tg_id = message.from_user.id
    choice = message.text.strip()

    # находим группу
    async with AsyncSessionLocal() as session:
        grp = (await session.execute(
            select(Group).where(Group.name == choice)
        )).scalar_one_or_none()

        if not grp:
            return await message.answer("Нажмите кнопку с названием вашей группы.")

        # сохраняем group_id у пользователя
        await session.execute(
            User.__table__.update()
            .where(User.tg_id == tg_id)
            .values(group_id=grp.id)
        )
        await session.commit()

    # завершаем FSM и удаляем клавиатуру
    await state.finish()
    await message.answer(
        f"Группа «{grp.name}» сохранена.",
        reply_markup=ReplyKeyboardRemove()
    )

    # перечитываем роль и рисуем главное меню
    async with AsyncSessionLocal() as session2:
        user = (await session2.execute(
            select(User).where(User.tg_id == tg_id)
        )).scalar_one()

    return await _send_main_menu(message, user.role)


async def _send_main_menu(message: types.Message, role: str):
    """
    Рисуем главное меню в зависимости от роли (без кнопки «Назад» и без «➕ Создать группу»).
    """
    kb = ReplyKeyboardMarkup(resize_keyboard=True)

    if role == "admin":
        kb.add(KeyboardButton("📊 Статистика"))
        kb.add(KeyboardButton("➕ Создать опрос"), KeyboardButton("🗑 Удалить опрос"))
        kb.add(KeyboardButton("✏️ Редактировать опрос"), KeyboardButton("📥 Экспорт результатов"))
        kb.add(KeyboardButton("👥 Управление пользователями"))

    elif role == "teacher":
        kb.add(KeyboardButton("➕ Создать опрос"), KeyboardButton("🗑 Удалить опрос"))
        kb.add(KeyboardButton("✏️ Редактировать опрос"), KeyboardButton("📥 Экспорт результатов"))
        kb.add(KeyboardButton("👥 Управление пользователями"))
        kb.add(KeyboardButton("📋 Пройти опрос"))

    else:  # student или unknown
        kb.add(KeyboardButton("📋 Пройти опрос"))

    return await message.answer("Выберите действие:", reply_markup=kb)


def register_start_handlers(dp: Dispatcher):
    dp.register_message_handler(cmd_start, commands=["start"], state="*")
    dp.register_message_handler(
        process_group_choice,
        state=SettingGroup.waiting_for_group
    )
