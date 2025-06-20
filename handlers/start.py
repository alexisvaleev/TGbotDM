# handlers/start.py

from aiogram import types, Dispatcher
from aiogram.dispatcher import FSMContext
from sqlalchemy.future import select
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

from database import AsyncSessionLocal
from models import User
from handlers.common import BACK_BTN


async def cmd_start(message: types.Message, state: FSMContext):
    """
    /start — если пользователь новый, создаём с ролью student
    и переводим его в FSM заполнения профиля, иначе — показываем
    главное меню под уже известную роль.
    """
    await state.finish()
    tg_id = message.from_user.id

    async with AsyncSessionLocal() as session:
        res = await session.execute(select(User).where(User.tg_id == tg_id))
        me = res.scalar_one_or_none()

        if not me:
            # Регистрация нового студента
            me = User(
                tg_id=tg_id,
                role="student",
                group_id=None,
                surname=None,
                name=None,
                patronymic=None
            )
            session.add(me)
            await session.commit()
            await session.refresh(me)

            # Локальный импорт, чтобы не создавать циклических зависимостей
            from handlers.profile import ask_profile
            return await ask_profile(message, state)

    # Уже есть в БД — строим меню
    return await _send_main_menu(message, me.role)


async def _send_main_menu(message: types.Message, role: str):
    """
    Выводит главное меню в зависимости от роли.
    Используется внутри cmd_start и в return_to_main_menu.
    """
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    if role == "admin":
        kb.add(KeyboardButton("📊 Статистика"))
        kb.add(KeyboardButton("➕ Создать опрос"), KeyboardButton("🗑 Удалить опрос"))
        kb.add(KeyboardButton("✏️ Редактировать опрос"), KeyboardButton("📥 Экспорт результатов"))
        kb.add(KeyboardButton("👥 Просмотр пользователей"), KeyboardButton("➕ Добавить пользователя"))
        kb.add(KeyboardButton("➕ Создать группу"), KeyboardButton("🔀 Назначить группу"))

    elif role == "teacher":
        kb.add(KeyboardButton("📊 Статистика"))
        kb.add(KeyboardButton("➕ Создать опрос"), KeyboardButton("🗑 Удалить опрос"))
        kb.add(KeyboardButton("✏️ Редактировать опрос"), KeyboardButton("📥 Экспорт результатов"))
        kb.add(KeyboardButton("👥 Просмотр пользователей"), KeyboardButton("➕ Добавить пользователя"))
        kb.add(KeyboardButton("➕ Создать группу"), KeyboardButton("🔀 Назначить группу"))
        kb.add(KeyboardButton("📋 Пройти опрос"))

    elif role == "student":
        kb.add(KeyboardButton("📋 Пройти опрос"))

    else:
        return await message.answer("⛔ У вас нет прав.", reply_markup=BACK_BTN)

    await message.answer("Выберите действие:", reply_markup=kb)


def register_start_handlers(dp: Dispatcher):
    dp.register_message_handler(cmd_start, commands=["start"], state="*")
