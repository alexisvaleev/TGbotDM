from aiogram import types
from aiogram.dispatcher.filters import CommandStart
from aiogram.dispatcher import FSMContext
from config import load_config
from database import AsyncSessionLocal
from models import User
from sqlalchemy.future import select
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
import os
from dotenv import load_dotenv

load_dotenv()

# Получаем список админов, студентов и учителей из .env
ADMIN_IDS = set(map(int, os.getenv("ADMIN_IDS", "").split(","))) if os.getenv("ADMIN_IDS") else set()
STUDENT_IDS = set(map(int, os.getenv("STUDENT_IDS", "").split(","))) if os.getenv("STUDENT_IDS") else set()
TEACHER_IDS = set(map(int, os.getenv("TEACHER_IDS", "").split(","))) if os.getenv("TEACHER_IDS") else set()


def get_user_keyboard():
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(KeyboardButton("📋 Пройти опрос"))
    return kb


async def cmd_start(message: types.Message, state: FSMContext):
    print(f"📥 /start от: {message.from_user.id}")
    await message.answer(f"Ваш Telegram ID: {message.from_user.id}")
    user_id = message.from_user.id

    async with AsyncSessionLocal() as session:
        result = await session.execute(select(User).where(User.tg_id == user_id))
        user = result.scalar()

        if user:
            await message.answer(f"Привет! Вы вошли как {user.role.capitalize()} ✅")
        else:
            # Присваиваем роль пользователю
            if user_id in ADMIN_IDS:
                role = "admin"
            elif user_id in STUDENT_IDS:
                role = "student"
            elif user_id in TEACHER_IDS:
                role = "teacher"
            else:
                role = "unknown"  # если не в одном из списков, присваиваем роль unknown

            user = User(tg_id=user_id, role=role)
            session.add(user)
            await session.commit()
            await message.answer(f"Добро пожаловать! Вы зарегистрированы как {role.capitalize()} ✅")

        # Важно: добавляем кнопки для пользователя
        if user.role == "admin":
            kb = ReplyKeyboardMarkup(resize_keyboard=True)
            kb.add(KeyboardButton("📊 Статистика"))
            kb.add(KeyboardButton("➕ Создать опрос"), KeyboardButton("🗑 Удалить опрос"))
            kb.add(KeyboardButton("👥 Управление пользователями"))
            await message.answer("Выберите действие:", reply_markup=kb)
        elif user.role == "student" or user.role == "teacher":
            # Если пользователь обычный студент/учитель
            kb = ReplyKeyboardMarkup(resize_keyboard=True)
            kb.add(KeyboardButton("📋 Пройти опрос"))
            print(f"User role: {user.role}, button added")
            await message.answer("Выберите действие:", reply_markup=kb)
        else:
            await message.answer("Ваш аккаунт не зарегистрирован для использования бота.")
