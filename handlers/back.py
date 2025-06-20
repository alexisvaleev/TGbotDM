# handlers/back.py

from aiogram import types
from sqlalchemy.future import select

from database import AsyncSessionLocal
from models import User


async def return_to_main_menu(message: types.Message):
    """
    Универсальная «🔙 Назад» — достаёт роль из БД
    и рисует меню через _send_main_menu.
    """
    tg_id = message.from_user.id
    async with AsyncSessionLocal() as session:
        res = await session.execute(select(User).where(User.tg_id == tg_id))
        me = res.scalar_one_or_none()

    # Импортируем только внутри, чтобы не создавать циклических ссылок
    from handlers.start import _send_main_menu
    role = me.role if me else None
    return await _send_main_menu(message, role)
