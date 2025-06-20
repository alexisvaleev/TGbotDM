# handlers/poll_take.py

from aiogram import types, Dispatcher
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import StatesGroup, State
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from models import PollCompletion
from sqlalchemy.future import select

from database import AsyncSessionLocal
from models import Poll, Question, Answer, Response, User
from .common import BACK, BACK_BTN
from .back   import return_to_main_menu

class PollTakeStates(StatesGroup):
    choosing_poll = State()
    answering     = State()

async def start_take_poll(message: types.Message, state: FSMContext):
    await state.finish()
    tg = message.from_user.id

    async with AsyncSessionLocal() as s:
        me = (await s.execute(
            select(User).where(User.tg_id == tg)
        )).scalar_one_or_none()

        if not me:
            return await message.answer("⛔ Вы не зарегистрированы.", reply_markup=BACK_BTN)

        role = me.role

        completed = (await s.execute(
            select(PollCompletion.poll_id)
            .where(PollCompletion.user_id == tg)
        )).scalars().all()

        polls = (await s.execute(
            select(Poll)
            .where(
                Poll.target_role.in_([role, "all"]),
                ~Poll.id.in_(completed)
            )
        )).scalars().all()

    if not polls:
        return await message.answer("🚫 Нет доступных опросов.", reply_markup=BACK_BTN)

    kb = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    for p in polls:
        kb.add(p.title)
    kb.add(BACK)

    await PollTakeStates.choosing_poll.set()
    await message.answer("Выберите опрос для прохождения:", reply_markup=kb)

async def process_poll_choice(message: types.Message, state: FSMContext):
    """
    Шаг 2: получили название опроса → готовим список вопросов и отправляем первый.
    """
    txt = message.text.strip()
    if txt == BACK:
        await state.finish()
        return await return_to_main_menu(message)

    # Находим опрос
    async with AsyncSessionLocal() as s:
        poll = (await s.execute(
            select(Poll).where(Poll.title == txt)
        )).scalar_one_or_none()
    if not poll:
        return await message.answer("❌ Опрос не найден.", reply_markup=BACK_BTN)

    # Загружаем все вопросы
    async with AsyncSessionLocal() as s:
        qs = (await s.execute(
            select(Question).where(Question.poll_id == poll.id)
        )).scalars().all()
    if not qs:
        return await message.answer("🚫 В этом опросе нет вопросов.", reply_markup=BACK_BTN)

    # Сохраняем в FSM: id опроса, список id вопросов и начальный индекс
    await state.update_data(
        poll_id=poll.id,
        question_ids=[q.id for q in qs],
        index=0
    )

    # Спрашиваем первый вопрос
    await _send_current_question(message, state)

async def _send_current_question(message: types.Message, state: FSMContext):
    data = await state.get_data()
    idx = data["index"]
    q_id = data["question_ids"][idx]

    # Достаём вопрос
    async with AsyncSessionLocal() as s:
        q = (await s.execute(
            select(Question).where(Question.id == q_id)
        )).scalar_one()

    # Если вариантный
    if q.question_type == "single_choice":
        async with AsyncSessionLocal() as s:
            opts = (await s.execute(
                select(Answer).where(Answer.question_id == q_id)
            )).scalars().all()
        kb = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        for o in opts:
            kb.add(o.answer_text)
        kb.add(BACK)
        await PollTakeStates.answering.set()
        await message.answer(q.question_text, reply_markup=kb)
    else:
        # Текстовый ответ
        await PollTakeStates.answering.set()
        await message.answer(q.question_text, reply_markup=ReplyKeyboardRemove())

async def process_answer(message: types.Message, state: FSMContext):
    """
    Шаг 3: сохраняем ответ и продолжаем или завершаем опрос.
    """
    txt = message.text.strip()
    data = await state.get_data()
    idx  = data["index"]
    q_id = data["question_ids"][idx]
    tg   = message.from_user.id

    # Назад?
    if txt == BACK:
        await state.finish()
        return await return_to_main_menu(message)

    # Получаем сам вопрос
    async with AsyncSessionLocal() as s:
        q = (await s.execute(
            select(Question).where(Question.id == q_id)
        )).scalar_one()

    # Определяем, какой ответ сохранять
    answer_id    = None
    response_txt = None
    if q.question_type == "single_choice":
        # Находим объект Answer по тексту
        async with AsyncSessionLocal() as s:
            a = (await s.execute(
                select(Answer)
                .where(Answer.question_id == q_id)
                .where(Answer.answer_text  == txt)
            )).scalar_one_or_none()
        if not a:
            return await message.answer("❌ Используйте кнопки.", reply_markup=BACK_BTN)
        answer_id = a.id
    else:
        response_txt = txt

    # Записываем в таблицу responses
    async with AsyncSessionLocal() as s:
        s.add(Response(
            user_id        = tg,
            question_id    = q_id,
            answer_id      = answer_id,
            response_text  = response_txt
        ))
        await s.commit()

    # Переходим к следующему вопросу
    idx += 1
    if idx >= len(data["question_ids"]):
        # Отмечаем прохождение опроса
        async with AsyncSessionLocal() as s:
            s.add(PollCompletion(user_id=tg, poll_id=data["poll_id"]))
            await s.commit()
        await state.finish()
        await message.answer("✅ Вы завершили опрос!", reply_markup=BACK_BTN)
        return await return_to_main_menu(message)

    await state.update_data(index=idx)
    return await _send_current_question(message, state)

def register_poll_take(dp: Dispatcher):
    dp.register_message_handler(
        start_take_poll,
        text="📋 Пройти опрос",
        state=None
    )
    dp.register_message_handler(
        process_poll_choice,
        state=PollTakeStates.choosing_poll
    )
    dp.register_message_handler(
        process_answer,
        state=PollTakeStates.answering
    )
