# handlers/back.py

from aiogram import types, Dispatcher
from aiogram.dispatcher import FSMContext
from sqlalchemy.future import select

from handlers.common import BACK
from database import AsyncSessionLocal
from models import User
from handlers.start import _send_main_menu


async def return_to_main_menu(message: types.Message):
    """Return to main menu according to user's role."""
    tg = message.from_user.id
    async with AsyncSessionLocal() as s:
        user = (await s.execute(select(User).where(User.tg_id == tg))).scalar()
    if not user:
        await message.answer("Пожалуйста, запустите /start.")
    else:
        await _send_main_menu(message, user.role)

async def go_back(message: types.Message, state: FSMContext):
    """Обработчик кнопки «Назад» — сбрасывает FSM и возвращает в главное меню."""
    await state.finish()
    await return_to_main_menu(message)

def register_back(dp: Dispatcher):
    dp.register_message_handler(go_back, text=BACK, state="*")
