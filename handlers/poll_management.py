# handlers/poll_management.py

from aiogram import types, Dispatcher
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.types import ReplyKeyboardMarkup

from sqlalchemy.future import select
from sqlalchemy import delete

from database import AsyncSessionLocal
from models import Poll  # больше не тянем UserPollProgress

from .common import BACK, BACK_BTN
from .back   import return_to_main_menu

class PollDeleteStates(StatesGroup):
    choosing_poll = State()

async def start_delete_poll(message: types.Message, state: FSMContext):
    """
    Шаг 1: показать список опросов для удаления.
    """
    # Завершаем любое текущее состояние
    await state.finish()

    # Получаем все опросы
    async with AsyncSessionLocal() as s:
        polls = (await s.execute(select(Poll))).scalars().all()

    if not polls:
        return await message.answer(
            "🚫 Нет опросов для удаления.",
            reply_markup=BACK_BTN
        )

    # Формируем клавиатуру из названий опросов
    kb = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    for p in polls:
        kb.add(p.title)
    kb.add(BACK)

    # Переходим в состояние выбора
    await PollDeleteStates.choosing_poll.set()
    await message.answer(
        "Выберите опрос, который хотите удалить:",
        reply_markup=kb
    )

async def process_delete_poll(message: types.Message, state: FSMContext):
    """
    Шаг 2: по выбору названия — удаляем опрос.
    """
    txt = message.text.strip()

    if txt == BACK:
        await state.finish()
        return await return_to_main_menu(message)

    # Ищем опрос по title
    async with AsyncSessionLocal() as s:
        poll = (await s.execute(
            select(Poll).where(Poll.title == txt)
        )).scalar_one_or_none()
        if not poll:
            return await message.answer(
                "❌ Опрос не найден.",
                reply_markup=BACK_BTN
            )
        # Удаляем через ORM (cascade удалит все вопросы/ответы)
        await s.delete(poll)
        await s.commit()

    # Завершаем FSM и возвращаем в главное меню
    await state.finish()
    await message.answer(
        f"✅ Опрос «{txt}» удалён.",
        reply_markup=BACK_BTN
    )
    return await return_to_main_menu(message)

def register_poll_management(dp: Dispatcher):
    # Старт удаления — только в state=None
    dp.register_message_handler(
        start_delete_poll,
        text="🗑 Удалить опрос",
        state=None
    )
    # Обработка выбора конкретного опроса
    dp.register_message_handler(
        process_delete_poll,
        state=PollDeleteStates.choosing_poll
    )
