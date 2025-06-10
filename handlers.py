from aiogram import types
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.dispatcher import FSMContext
from database import AsyncSessionLocal
from models import User, Poll, Question, Answer, UserPollProgress, UserAnswer
from sqlalchemy.future import select
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove

class PollTaking(StatesGroup):
    choosing_poll = State()  # Состояние выбора опроса
    answering_questions = State()  # Состояние прохождения опроса

# Хранение состояния для пользователя в процессе прохождения опроса
user_poll_state = {}

async def start_poll_taking(message: types.Message, state: FSMContext):
    user_id = message.from_user.id

    # Отладочный вывод
    print(f"start_poll_taking: {user_id}")

    async with AsyncSessionLocal() as session:
        result = await session.execute(select(User).where(User.tg_id == user_id))
        user = result.scalar()

        # Получаем список опросов, которые доступны пользователю
        completed_result = await session.execute(
            select(UserPollProgress.poll_id).where(
                UserPollProgress.user_id == user.id,
                UserPollProgress.is_completed == True,
            )
        )
        completed_poll_ids = [row[0] for row in completed_result.fetchall()]

        polls_result = await session.execute(
            select(Poll).where(
                ((Poll.target_role == user.role) | (Poll.target_role == "все"))
                & (~Poll.id.in_(completed_poll_ids))
            )
        )
        polls = polls_result.scalars().all()

        if not polls:
            return await message.answer("Нет доступных опросов.")

        text = "Доступные опросы:\n"
        for idx, poll in enumerate(polls, start=1):
            text += f"{idx}. {poll.title}\n"

        user_poll_state[user_id] = {"polls": polls}  # Сохраняем доступные опросы в состояние

        await state.set_state(PollTaking.choosing_poll.state)
        await message.answer(text + "\nВведите номер опроса, который хотите пройти:")

async def choose_poll(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    print(f"choose_poll: {user_id}, message={message.text}")  # Отладка

    if not message.text.isdigit():
        return await message.answer("Пожалуйста, введите номер из списка.")

    index = int(message.text) - 1
    user_data = user_poll_state.get(user_id)
    if not user_data or index >= len(user_data["polls"]):
        return await message.answer("Некорректный номер опроса.")

    selected_poll = user_data["polls"][index]
    user_data["poll_id"] = selected_poll.id
    user_data["current_q"] = 0  # Начинаем с первого вопроса

    async with AsyncSessionLocal() as session:
        # Получаем все вопросы для выбранного опроса
        questions = (await session.execute(select(Question).where(Question.poll_id == selected_poll.id))).scalars().all()
        user_data["questions"] = questions  # Сохраняем вопросы в состояние
        user_data["answers"] = []  # Очистим список ответов

    print(f"Selected Poll: {selected_poll.title}, Questions: {len(user_data['questions'])}")  # Отладка

    await state.set_state(PollTaking.answering_questions.state)
    await send_next_question(message, state)

async def send_next_question(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    user_data = user_poll_state[user_id]
    current_q_index = user_data["current_q"]
    questions = user_data["questions"]

    # Отладка
    print(f"send_next_question: {user_id}, current_q_index={current_q_index}, total_questions={len(questions)}")

    if current_q_index >= len(questions):  # Если вопросы закончились
        await finish_poll(message, state)
        return

    question = questions[current_q_index]
    user_data["current_question"] = question

    async with AsyncSessionLocal() as session:
        answers = (await session.execute(select(Answer).where(Answer.question_id == question.id))).scalars().all()

    if answers:
        markup = ReplyKeyboardMarkup(resize_keyboard=True)
        for ans in answers:
            markup.add(KeyboardButton(ans.answer_text))
        if question.question_type == 'text':  # Если вопрос типа текст
            markup.add(KeyboardButton("✍️ Свой вариант"))
        await message.answer(f"❓ {question.question_text}", reply_markup=markup)
    else:
        await message.answer(f"❓ {question.question_text}", reply_markup=ReplyKeyboardRemove())

async def process_answer(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    user_data = user_poll_state[user_id]
    question = user_data["current_question"]
    text = message.text.strip()

    print(f"process_answer: {user_id}, answer_text={text}")  # Отладка

    if text == "✍️ Свой вариант":  # Если пользователь выбрал "свой вариант"
        await message.answer("Напишите свой вариант ответа:")
        return

    # Сохраняем ответ пользователя
    user_data["answers"].append((question.id, text))
    user_data["current_q"] += 1  # Переходим к следующему вопросу
    await send_next_question(message, state)

async def finish_poll(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    user_data = user_poll_state[user_id]

    print(f"finish_poll: {user_id}, poll_id={user_data['poll_id']}")  # Отладка

    async with AsyncSessionLocal() as session:
        # Сохраняем результаты опроса
        progress = UserPollProgress(user_id=user_id, poll_id=user_data["poll_id"], is_completed=True)
        session.add(progress)

        for q_id, ans_text in user_data["answers"]:
            session.add(UserAnswer(user_id=user_id, question_id=q_id, answer_text=ans_text))

        await session.commit()

    await message.answer("✅ Опрос завершён. Спасибо за участие!", reply_markup=ReplyKeyboardRemove())
    await state.finish()  # Завершаем состояние
    user_poll_state.pop(user_id, None)  # Удаляем состояние пользователя

# Регистрация хендлеров
def register_handlers(dp):
    dp.register_message_handler(start_poll_taking, text="📋 Пройти опрос", state="*")
    dp.register_message_handler(choose_poll, state=PollTaking.choosing_poll)
    dp.register_message_handler(process_answer, state=PollTaking.answering_questions)
