# handlers/start.py

from aiogram import types, Dispatcher
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import StatesGroup, State
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from sqlalchemy.future import select

from config import load_config
from database import AsyncSessionLocal
from models import User, Group

config = load_config()

class SettingGroup(StatesGroup):
    waiting_for_group = State()


async def cmd_start(message: types.Message, state: FSMContext):
    await state.finish()
    tg_id = message.from_user.id

    # 1) Проверяем пользователя в БД
    async with AsyncSessionLocal() as ses:
        user = (await ses.execute(
            select(User).where(User.tg_id == tg_id)
        )).scalar_one_or_none()
        if not user:
            # определяем роль
            if   tg_id in config.ADMIN_IDS:
                role = "admin"
            elif tg_id in config.TEACHER_IDS:
                role = "teacher"
            elif tg_id in config.STUDENT_IDS:
                role = "student"
            else:
                role = "unknown"
            user = User(tg_id=tg_id, role=role)
            ses.add(user)
            await ses.commit()

    # 2) Если teacher/student без группы — спрашиваем группу
    if user.role in ("teacher","student") and not user.group_id:
        async with AsyncSessionLocal() as ses2:
            groups = (await ses2.execute(select(Group))).scalars().all()
        kb = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        for g in groups:
            kb.add(KeyboardButton(g.name))
        await SettingGroup.waiting_for_group.set()
        return await message.answer("Пожалуйста, выберите вашу группу:", reply_markup=kb)

    # 3) Иначе — рисуем меню
    return await _send_main_menu(message, user.role)


async def process_group_choice(message: types.Message, state: FSMContext):
    tg_id = message.from_user.id
    choice = message.text.strip()

    async with AsyncSessionLocal() as ses:
        grp = (await ses.execute(
            select(Group).where(Group.name == choice)
        )).scalar_one_or_none()
        if not grp:
            return await message.answer("Нажмите кнопку с названием вашей группы.")
        # сохраняем
        await ses.execute(
            User.__table__.update()
            .where(User.tg_id == tg_id)
            .values(group_id=grp.id)
        )
        await ses.commit()

    await state.finish()
    await message.answer(f"Группа «{grp.name}» сохранена.", reply_markup=ReplyKeyboardRemove())

    # заново рисуем меню
    async with AsyncSessionLocal() as ses2:
        user = (await ses2.execute(
            select(User).where(User.tg_id == tg_id)
        )).scalar_one()
    return await _send_main_menu(message, user.role)


async def _send_main_menu(message: types.Message, role: str):
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

    elif role == "student":
        kb.add(KeyboardButton("📋 Пройти опрос"))

    else:  # unknown
        return await message.answer("⛔ У вас нет прав на это действие.")

    return await message.answer("Выберите действие:", reply_markup=kb)


def register_start_handlers(dp: Dispatcher):
    dp.register_message_handler(cmd_start, commands=["start"], state="*")
    dp.register_message_handler(process_group_choice, state=SettingGroup.waiting_for_group)
