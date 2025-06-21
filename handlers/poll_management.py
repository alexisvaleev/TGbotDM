# handlers/poll_management.py

from aiogram import types, Dispatcher
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup

from sqlalchemy import delete
from sqlalchemy.future import select

from database import AsyncSessionLocal
from models import Poll, PollCompletion
from .common import BACK
from .back import return_to_main_menu

class PollDeleteStates(StatesGroup):
    choosing_poll = State()

async def start_delete_poll(message: types.Message, state: FSMContext):
    """
    Шаг 1: вывести список опросов для удаления.
    """
    await state.finish()
    # Получаем все опросы
    async with AsyncSessionLocal() as s:
        polls = (await s.execute(select(Poll))).scalars().all()

    if not polls:
        # Нет опросов — сразу в главное меню
        return await return_to_main_menu(message)

    # Строим клавиатуру с названиями опросов + «Назад»
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    for p in polls:
        kb.add(p.title)
    kb.add(BACK)

    await PollDeleteStates.choosing_poll.set()
    await message.answer(
        "🗑 Выберите опрос для удаления:",
        reply_markup=kb
    )

async def process_delete_poll(message: types.Message, state: FSMContext):
    """
    Шаг 2: обработать выбор и удалить опрос + связанные PollCompletion.
    """
    text = message.text.strip()

    # Если нажали «Назад» — завершаем FSM и возвращаем главное меню
    if text == BACK:
        await state.finish()
        return await return_to_main_menu(message)

    # Ищем опрос по названию
    async with AsyncSessionLocal() as s:
        poll = (await s.execute(
            select(Poll).where(Poll.title == text)
        )).scalar_one_or_none()

        if not poll:
            # Если не нашли — остаёмся в том же состоянии
            kb = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
            kb.add(BACK)
            return await message.answer(
                "❌ Опрос не найден. Попробуйте ещё раз или нажмите «🔙 Назад».",
                reply_markup=kb
            )

        # Удаляем все записи о прохождении опроса
        await s.execute(
            delete(PollCompletion).where(PollCompletion.poll_id == poll.id)
        )
        # Удаляем сам опрос (вопросы/ответы через cascade в модели)
        await s.delete(poll)
        await s.commit()

    # Завершаем FSM и возвращаем в главное меню с подтверждением
    await state.finish()
    await message.answer(
        f"✅ Опрос «{text}» успешно удалён.",
        reply_markup=types.ReplyKeyboardRemove()
    )
    return await return_to_main_menu(message)

def register_poll_management(dp: Dispatcher):
    dp.register_message_handler(
        start_delete_poll,
        text="🗑 Удалить опрос",
        state=None
    )
    dp.register_message_handler(
        process_delete_poll,
        state=PollDeleteStates.choosing_poll
    )
