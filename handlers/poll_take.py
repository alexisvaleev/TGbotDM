# handlers/poll_take.py

from aiogram import types, Dispatcher
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from sqlalchemy import select, update
from database import AsyncSessionLocal
from models import User, Poll, Question, Answer, UserAnswer, UserPollProgress


class StudentPollStates(StatesGroup):
    choosing_poll = State()    # ждём, что студент выберет опрос
    answering     = State()    # ждём, что студент нажмёт кнопку-ответ


async def start_poll_taking(message: types.Message, state: FSMContext):
    """Обработчик для кнопки '📋 Пройти опрос'. Показывает список доступных опросов."""
    await state.finish()  # Сбрасываем старые состояния
    await message.answer("Ищем доступные опросы…", reply_markup=ReplyKeyboardRemove())

    tg_id = message.from_user.id
    async with AsyncSessionLocal() as session:
        user = (await session.execute(select(User).where(User.tg_id == tg_id))).scalar()
        if not user:
            return await message.answer("❌ Сначала зарегистрируйтесь через /start.")

        polls = (await session.execute(
            select(Poll).where(
                (Poll.target_role == user.role) | (Poll.target_role == "все"),
                (Poll.group_id.is_(None)) | (Poll.group_id == user.group_id)
            )
        )).scalars().all()

    if not polls:
        return await message.answer("❌ Нет доступных опросов.")

    kb = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    for i, p in enumerate(polls, 1):
        kb.add(KeyboardButton(f"{i}. {p.title}"))

    await state.update_data(poll_ids=[p.id for p in polls])
    await state.set_state(StudentPollStates.choosing_poll)
    await message.answer("📋 Выберите опрос:", reply_markup=kb)


async def choose_poll(message: types.Message, state: FSMContext):
    """Студент выбрал опрос. Создаём запись прогресса и задаём первый вопрос."""
    data = await state.get_data()
    poll_ids = data.get("poll_ids", [])

    text = message.text.split(".")[0]
    if not text.isdigit():
        return await message.answer("Пожалуйста, нажмите кнопку с номером опроса.")
    idx = int(text) - 1
    if idx < 0 or idx >= len(poll_ids):
        return await message.answer("Неверный выбор.")

    poll_id = poll_ids[idx]

    tg_id = message.from_user.id
    async with AsyncSessionLocal() as session:
        user = (await session.execute(select(User).where(User.tg_id == tg_id))).scalar()
        progress = UserPollProgress(
            user_id=user.id, poll_id=poll_id,
            last_question_id=None, is_completed=False
        )
        session.add(progress)
        await session.commit()

    await state.update_data(poll_id=poll_id, progress_id=progress.id, q_index=0)
    await _ask_question(message, state)


async def _ask_question(message: types.Message, state: FSMContext):
    """Выдаёт следующий вопрос и варианты ответа."""
    data = await state.get_data()
    poll_id = data["poll_id"]
    q_index = data["q_index"]

    async with AsyncSessionLocal() as session:
        questions = (await session.execute(select(Question).where(Question.poll_id == poll_id))).scalars().all()

    if q_index >= len(questions):
        return await _finish_poll(message, state)

    question = questions[q_index]

    async with AsyncSessionLocal() as session:
        options = (await session.execute(select(Answer).where(Answer.question_id == question.id))).scalars().all()

    kb = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    for opt in options:
        kb.add(KeyboardButton(opt.answer_text))

    await state.set_state(StudentPollStates.answering)
    await message.answer(question.question_text, reply_markup=kb)


async def process_answer(message: types.Message, state: FSMContext):
    """Сохраняем ответ студента и переходим к следующему вопросу."""
    data = await state.get_data()
    poll_id     = data["poll_id"]
    progress_id = data["progress_id"]
    q_index     = data["q_index"]

    async with AsyncSessionLocal() as session:
        questions = (await session.execute(select(Question).where(Question.poll_id == poll_id))).scalars().all()
    question = questions[q_index]

    text = message.text.strip()
    async with AsyncSessionLocal() as session:
        valid = (await session.execute(select(Answer).where(
            Answer.question_id == question.id,
            Answer.answer_text == text
        ))).scalar()
    if not valid:
        return await message.answer("Выберите вариант кнопкой, пожалуйста.")

    tg_id = message.from_user.id
    async with AsyncSessionLocal() as session:
        user = (await session.execute(select(User).where(User.tg_id == tg_id))).scalar()
        ua = UserAnswer(user_id=user.id, question_id=question.id, answer_text=text)
        session.add(ua)
        await session.execute(update(UserPollProgress).where(UserPollProgress.id == progress_id).values(last_question_id=question.id))
        await session.commit()

    await state.update_data(q_index=q_index + 1)
    await _ask_question(message, state)


async def _finish_poll(message: types.Message, state: FSMContext):
    """Завершаем опрос, убираем клавиатуру и благодарим студента."""
    data = await state.get_data()
    progress_id = data["progress_id"]

    async with AsyncSessionLocal() as session:
        await session.execute(update(UserPollProgress).where(UserPollProgress.id == progress_id).values(is_completed=True))
        await session.commit()

    await message.answer("🎉 Опрос завершён. Спасибо за участие!", reply_markup=ReplyKeyboardRemove())
    await state.finish()


def register_poll_take(dp: Dispatcher):
    dp.register_message_handler(start_poll_taking, text="📋 Пройти опрос", state="*")
    dp.register_message_handler(choose_poll, state=StudentPollStates.choosing_poll)
    dp.register_message_handler(process_answer, state=StudentPollStates.answering)
