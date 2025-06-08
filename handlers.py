from aiogram import types, Dispatcher
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from sqlalchemy.future import select
from models import User, Poll, Question, Answer, UserAnswer, UserPollProgress
from database import AsyncSessionLocal

# FSM для прохождения опроса
class PollTaking(StatesGroup):
    choosing_poll = State()
    answering_questions = State()

async def start_poll_taking(message: types.Message, state: FSMContext):
    user_id = message.from_user.id

    async with AsyncSessionLocal() as session:
        result = await session.execute(select(User).where(User.tg_id == user_id))
        user = result.scalar()

        # Получаем только те опросы, которые доступны для данного пользователя
        completed_result = await session.execute(
            select(UserPollProgress.poll_id).where(
                UserPollProgress.user_id == user.id,
                UserPollProgress.is_completed == True
            )
        )
        completed_poll_ids = [row[0] for row in completed_result.fetchall()]

        polls_result = await session.execute(
            select(Poll).where(
                ((Poll.target_role == user.role) | (Poll.target_role == "все")) &
                (~Poll.id.in_(completed_poll_ids))
            )
        )
        polls = polls_result.scalars().all()

        if not polls:
            return await message.answer("Нет доступных опросов.")

        text = "Доступные опросы:\n"
        for idx, poll in enumerate(polls, start=1):
            text += f"{idx}. {poll.title}\n"

        await state.update_data(polls=polls)
        await state.set_state(PollTaking.choosing_poll.state)
        await message.answer(text + "\nВведите номер опроса, который хотите пройти:")

@dp.message_handler(state=PollTaking.choosing_poll)
async def choose_poll(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    if not message.text.isdigit():
        return await message.answer("Пожалуйста, введите номер из списка.")

    index = int(message.text) - 1
    user_data = await state.get_data()
    polls = user_data.get('polls', [])
    if not polls or index >= len(polls):
        return await message.answer("Некорректный номер опроса.")

    selected_poll = polls[index]
    await state.update_data(selected_poll=selected_poll)

    async with AsyncSessionLocal() as session:
        questions = (await session.execute(
            select(Question).where(Question.poll_id == selected_poll.id)
        )).scalars().all()

    await state.update_data(questions=questions)
    await state.set_state(PollTaking.answering_questions.state)
    await send_next_question(message, state)

async def send_next_question(message: types.Message, state: FSMContext):
    user_data = await state.get_data()
    questions = user_data.get("questions", [])
    current_q_index = user_data.get("current_q", 0)

    if current_q_index >= len(questions):
        await finish_poll(message, state)
        return

    question = questions[current_q_index]
    await state.update_data(current_question=question)

    markup = ReplyKeyboardMarkup(resize_keyboard=True)
    answers = await get_answers_for_question(question.id)

    for answer in answers:
        markup.add(KeyboardButton(answer.text))

    await message.answer(f"❓ {question.question_text}", reply_markup=markup)

async def get_answers_for_question(question_id):
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Answer).where(Answer.question_id == question_id))
        answers = result.scalars().all()
    return answers

@dp.message_handler(state=PollTaking.answering_questions)
async def process_answer(message: types.Message, state: FSMContext):
    user_data = await state.get_data()
    current_question = user_data.get("current_question")
    user_id = message.from_user.id
    answer_text = message.text.strip()

    async with AsyncSessionLocal() as session:
        answer = UserAnswer(user_id=user_id, question_id=current_question.id, answer_text=answer_text)
        session.add(answer)
        await session.commit()

    current_q_index = user_data.get("current_q", 0) + 1
    await state.update_data(current_q=current_q_index)
    await send_next_question(message, state)

async def finish_poll(message: types.Message, state: FSMContext):
    user_data = await state.get_data()
    selected_poll = user_data.get('selected_poll')
    user_id = message.from_user.id

    async with AsyncSessionLocal() as session:
        progress = UserPollProgress(user_id=user_id, poll_id=selected_poll.id, is_completed=True)
        session.add(progress)
        await session.commit()

    await message.answer("✅ Опрос завершён. Спасибо за участие!", reply_markup=ReplyKeyboardRemove())
    await state.finish()
