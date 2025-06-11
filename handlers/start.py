from dotenv import load_dotenv
from aiogram import types
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from sqlalchemy.future import select

from database import AsyncSessionLocal
from models import User, Group
from config import ADMIN_IDS, TEACHER_IDS, STUDENT_IDS

load_dotenv()

class SettingGroup(StatesGroup):
    waiting_for_group = State()

async def add_users_to_db(dp):
    # Добавляем админов/учителей/студентов из .env, если их нет в БД
    async with AsyncSessionLocal() as session:
        existing = {u.tg_id for u in (await session.execute(select(User))).scalars().all()}
        all_users = {(tg, 'admin') for tg in ADMIN_IDS} | \
                    {(tg, 'teacher') for tg in TEACHER_IDS} | \
                    {(tg, 'student') for tg in STUDENT_IDS}

        for tg_id, role in all_users:
            if tg_id not in existing:
                session.add(User(tg_id=tg_id, role=role))
        await session.commit()

async def cmd_start(message: types.Message, state: FSMContext):
    tg_id = message.from_user.id
    async with AsyncSessionLocal() as session:
        # Проверяем, есть ли пользователь
        result = await session.execute(select(User).where(User.tg_id == tg_id))
        user = result.scalar()

        if not user:
            # Новый пользователь
            if tg_id in ADMIN_IDS:
                role = "admin"
            elif tg_id in TEACHER_IDS:
                role = "teacher"
            elif tg_id in STUDENT_IDS:
                role = "student"
            else:
                role = "unknown"
            user = User(tg_id=tg_id, role=role)
            session.add(user)
            await session.commit()

        # Если студент/учитель и группа не указана — спрашиваем её
        if user.role in ("student", "teacher") and not user.group_id:
            # Получаем все группы из БД
            groups = (await session.execute(select(Group))).scalars().all()
            kb = ReplyKeyboardMarkup(resize_keyboard=True)
            for g in groups:
                kb.add(KeyboardButton(g.name))
            await state.set_state(SettingGroup.waiting_for_group.state)
            return await message.answer("Выберите вашу группу:", reply_markup=kb)

        # Иначе сразу показываем меню
        await _send_main_menu(message, user.role)


async def process_group_choice(message: types.Message, state: FSMContext):
    tg_id = message.from_user.id
    chosen = message.text.strip()
    async with AsyncSessionLocal() as session:
        # находим группу
        result = await session.execute(select(Group).where(Group.name == chosen))
        group = result.scalar()
        if not group:
            return await message.answer("Неверная группа, выберите из списка.")
        # обновляем пользователя
        await session.execute(
            User.__table__.update()
            .where(User.tg_id == tg_id)
            .values(group_id=group.id)
        )
        await session.commit()
    await state.finish()
    await message.answer(f"Группа «{group.name}» сохранена.", reply_markup=ReplyKeyboardRemove())
    # отправляем главное меню
    # узнаём роль
    async with AsyncSessionLocal() as session2:
        user = (await session2.execute(select(User).where(User.tg_id == tg_id))).scalar()
    await _send_main_menu(message, user.role)


async def _send_main_menu(message: types.Message, role: str):
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    if role == "admin":
        # kb.add(KeyboardButton("📊 Статистика"))
        kb.add(KeyboardButton("➕ Создать опрос"), KeyboardButton("🗑 Удалить опрос"))
        kb.add(KeyboardButton("📥 Экспорт результатов"))
        kb.add(KeyboardButton("✏️ Редактировать опрос"))
        # kb.add(KeyboardButton("👥 Управление пользователями"))
    elif role in ("teacher", "student"):

        kb.add(KeyboardButton("📋 Пройти опрос"))
    else:
        return await message.answer("⛔ У вас нет прав для использования бота.")
    await message.answer("Выберите действие:", reply_markup=kb)
