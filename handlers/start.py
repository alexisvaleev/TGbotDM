import os
from dotenv import load_dotenv

from aiogram import types
from aiogram.dispatcher import FSMContext
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from sqlalchemy.future import select

from database import AsyncSessionLocal
from models import User
from config import ADMIN_IDS, TEACHER_IDS, STUDENT_IDS

load_dotenv()

async def add_users_to_db(dp):
    """
    Автоматически добавляет всех tg_id из ADMIN_IDS, TEACHER_IDS, STUDENT_IDS в таблицу users.
    """
    print("▶️ Запуск add_users_to_db()")
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(User))
        existing = {u.tg_id for u in result.scalars().all()}

        all_users = {
            (tg, 'admin') for tg in ADMIN_IDS
        } | {
            (tg, 'teacher') for tg in TEACHER_IDS
        } | {
            (tg, 'student') for tg in STUDENT_IDS
        }

        for tg_id, role in all_users:
            if tg_id not in existing:
                user = User(tg_id=tg_id, role=role)
                session.add(user)
                print(f"✅ Добавлен пользователь {tg_id} → роль {role}")

        await session.commit()
        print("✅ Все пользователи из .env добавлены в БД")


async def cmd_start(message: types.Message, state: FSMContext):
    """
    Обработчик команды /start — регистрирует пользователя в БД (если его ещё нет),
    показывает роль и меню в зависимости от роли.
    """
    tg_id = message.from_user.id
    print(f"📥 /start от: {tg_id}")

    async with AsyncSessionLocal() as session:
        result = await session.execute(select(User).where(User.tg_id == tg_id))
        user = result.scalar()

        # Если пользователя нет — создаём
        if not user:
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
            print(f"✅ Зарегистрирован новый пользователь {tg_id} → {role}")

        # Приветственное сообщение
        await message.answer(f"Привет, вы вошли как {user.role.capitalize()} ✅")

        # Формируем клавиатуру в зависимости от роли
        kb = ReplyKeyboardMarkup(resize_keyboard=True)
        if user.role == "admin":
            kb.add(KeyboardButton("📊 Статистика"))
            kb.add(KeyboardButton("➕ Создать опрос"), KeyboardButton("🗑 Удалить опрос"))
            kb.add(KeyboardButton("👥 Управление пользователями"))
        elif user.role in ("teacher", "student"):
            kb.add(KeyboardButton("📋 Пройти опрос"))
        else:
            await message.answer("⛔ У вас нет прав для работы с ботом.")
            return

        await message.answer("Выберите действие:", reply_markup=kb)
