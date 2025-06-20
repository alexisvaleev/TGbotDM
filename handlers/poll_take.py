# handlers/poll_take.py

from aiogram import types, Dispatcher
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.types import (
    ReplyKeyboardRemove,
    ReplyKeyboardMarkup,
    KeyboardButton
)
from sqlalchemy import or_
from sqlalchemy.future import select

from database import AsyncSessionLocal
from models import (
    User,
    Poll,
    Question,
    Answer,
    UserPollProgress,
    UserAnswer
)
from handlers.common import BACK, BACK_BTN
from handlers.back import return_to_main_menu


class TakePollStates(StatesGroup):
    choosing_poll = State()
    answering     = State()


async def start_take_poll(message: types.Message, state: FSMContext):
    """Запускается по кнопке 📋 Пройти опрос."""
    await state.finish()
    tg_id = message.from_user.id

    # грузим пользователя
    async with AsyncSessionLocal() as s:
        me = (await s.execute(
            select(User).where(User.tg_id == tg_id)
        )).scalar_one_or_none()

    # разрешаем и студентам, и учителям
    if not me or me.role not in ("student", "teacher"):
        return await message.answer("⛔ Только студент или преподаватель может проходить опросы.")

    await message.answer("🔍 Ищем доступные опросы…")

    # ищем опросы, которые:
    # – таргетятся на эту роль или на всех
    # – и либо без группы, либо на группу пользователя
    async with AsyncSessionLocal() as s:
        q = select(Poll).where(
            Poll.target_role.in_([me.role, "all"]),
            or_(Poll.group_id.is_(None), Poll.group_id == me.group_id)
        )
        polls = (await s.execute(q)).scalars().all()

        # исключаем уже пройденные
        done = (await s.execute(
            select(UserPollProgress.poll_id).where(UserPollProgress.user_id == me.id)
        )).scalars().all()
    polls = [p for p in polls if p.id not in done]

    if not polls:
        return await message.answer("🚫 Нет доступных опросов.", reply_markup=BACK_BTN)

    # рисуем клавиатуру выбора
    kb = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    for i, p in enumerate(polls, start=1):
        kb.add(KeyboardButton(f"{i}. {p.title}"))
    kb.add(BACK_BTN)

    await state.update_data(poll_ids=[p.id for p in polls])
    await TakePollStates.choosing_poll.set()
    await message.answer("Выберите опрос:", reply_markup=kb)


async def choose_poll_to_take(message: types.Message, state: FSMContext):
    data = await state.get_data()
    poll_ids = data.get("poll_ids", [])
    text = message.text.strip()

    if text == BACK:
        await state.finish()
        return await return_to_main_menu(message)
    if not text.split(".", 1)[0].isdigit():
        return await message.answer("Пожалуйста, выберите опрос кнопкой.", reply_markup=BACK_BTN)

    idx = int(text.split(".", 1)[0]) - 1
    if idx < 0 or idx >= len(poll_ids):
        return await message.answer("Неверный номер.", reply_markup=BACK_BTN)

    poll_id = poll_ids[idx]
    await state.update_data(chosen_poll=poll_id)

    # стартуем проход
    return await _ask_next_question(message, state)


async def _ask_next_question(message: types.Message, state: FSMContext):
    data = await state.get_data()
    poll_id = data["chosen_poll"]
    tg_id   = message.from_user.id

    # получаем пользователя и прогресс
    async with AsyncSessionLocal() as s:
        me = (await s.execute(
            select(User).where(User.tg_id == tg_id)
        )).scalar_one()
        prog = (await s.execute(
            select(UserPollProgress).where(
                UserPollProgress.user_id == me.id,
                UserPollProgress.poll_id == poll_id
            )
        )).scalar_one_or_none()

        # если ещё нет – создаём
        if not prog:
            prog = UserPollProgress(user_id=me.id, poll_id=poll_id, last_question_id=None)
            s.add(prog)
            await s.flush()

        # ищем очередной вопрос
        q = select(Question).where(Question.poll_id == poll_id)
        if prog.last_question_id:
            q = q.where(Question.id > prog.last_question_id)
        q = q.order_by(Question.id).limit(1)
        next_q = (await s.execute(q)).scalar_one_or_none()

        # если вопросов нет – завершаем
        if not next_q:
            prog.is_completed = 1
            await s.commit()
            await message.answer("✅ Вы успешно прошли опрос!", reply_markup=ReplyKeyboardRemove())
            await state.finish()
            return await return_to_main_menu(message)

        # задаём вопрос
        prog.last_question_id = next_q.id
        await s.commit()

        # строим клавиатуру вариантов (если есть)
        if next_q.question_type == "single_choice":
            opts = (await s.execute(
                select(Answer).where(Answer.question_id == next_q.id)
            )).scalars().all()
            kb = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
            for o in opts:
                kb.add(KeyboardButton(o.answer_text))
            kb.add(BACK_BTN)
            await state.update_data(current_q=next_q.id)
            await TakePollStates.answering.set()
            return await message.answer(next_q.question_text, reply_markup=kb)

        # иначе просто текстовый ввод
        await state.update_data(current_q=next_q.id)
        await TakePollStates.answering.set()
        return await message.answer(next_q.question_text, reply_markup=BACK_BTN)


async def process_answer(message: types.Message, state: FSMContext):
    data = await state.get_data()
    txt    = message.text.strip()
    q_id   = data.get("current_q")
    p_id   = data.get("chosen_poll")
    tg_id  = message.from_user.id

    # BACK?
    if txt == BACK:
        await state.finish()
        return await return_to_main_menu(message)

    # сохраняем ответ
    async with AsyncSessionLocal() as s:
        me = (await s.execute(
            select(User).where(User.tg_id == tg_id)
        )).scalar_one()
        s.add(UserAnswer(user_id=me.id, question_id=q_id, answer_text=txt))
        await s.commit()

    # и задаём следующий
    return await _ask_next_question(message, state)


def register_poll_take(dp: Dispatcher):
    dp.register_message_handler(start_take_poll, text="📋 Пройти опрос", state="*")
    dp.register_message_handler(choose_poll_to_take, state=TakePollStates.choosing_poll)
    dp.register_message_handler(process_answer,     state=TakePollStates.answering)
