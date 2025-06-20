from aiogram import types, Dispatcher
from aiogram.types import ReplyKeyboardRemove
from sqlalchemy.future import select

from database import AsyncSessionLocal
from models import User
from .menu import send_main_menu

async def cmd_start(message: types.Message):
    tg = message.from_user.id
    async with AsyncSessionLocal() as s:
        me = (await s.execute(
            select(User).where(User.tg_id == tg)
        )).scalar_one_or_none()
    if not me:
        return await message.answer(
            "⛔ Вы не зарегистрированы. Обратитесь к администратору.",
            reply_markup=ReplyKeyboardRemove()
        )
    return await send_main_menu(message)

def register_start_handlers(dp: Dispatcher):
    dp.register_message_handler(cmd_start, commands=["start"], state="*")
