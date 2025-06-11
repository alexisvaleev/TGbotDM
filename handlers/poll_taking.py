from aiogram import types
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.dispatcher import FSMContext
from database import AsyncSessionLocal
from models import User, Poll, Question, Answer, UserPollProgress, UserAnswer
from sqlalchemy.future import select
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove

class PollTaking(StatesGroup):
    choosing_poll = State()
    answering_questions = State()

user_poll_state = {}

async def start_poll_taking(message: types.Message, state: FSMContext):
    user_id = message.from_user.id

    # Отладочный вывод
    print(f"start_poll_taking: Получаем список опросов для пользователя {user_id}")

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
        print(f"completed_poll_ids: {completed_poll_ids}")  # Логируем завершённые опросы

        polls_result = await session.execute(
            select(Poll).where(
                ((Poll.target_role == user.role) | (Poll.target_role == "все"))
                & (~Poll.id.in_(completed_poll_ids))
            )
        )
        polls = polls_result.scalars().all()

        if not polls:
            print("Нет доступных опросов.")  # Логируем, если нет доступных опросов
            return await message.answer("Нет доступных опросов.")

        text = "Доступные опросы:\n"
        for idx, poll in enumerate(polls, start=1):
            text += f"{idx}. {poll.title}\n"

        user_poll_state[user_id] = {"polls": polls}  # Сохраняем доступные опросы в состояние

        await state.set_state(PollTaking.choosing_poll.state)
        print(f"Отправляю список опросов пользователю {user_id}")
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

    print(f"Selected Poll: {selected_poll.title}, poll_id: {selected_poll.id}")  # Отладка

    async with AsyncSessionLocal() as session:
        # Получаем все вопросы для выбранного опроса
        questions = (await session.execute(select(Question).where(Question.poll_id == selected_poll.id))).scalars().all()
        user_data["questions"] = questions  # Сохраняем вопросы в состояние
        user_data["answers"] = []  # Очистим список ответов

    print(f"Retrieved {len(user_data['questions'])} questions for poll ID {selected_poll.id}")  # Отладка

    if not user_data["questions"]:
        return await message.answer("Нет вопросов в этом опросе.")

    await state.set_state(PollTaking.answering_questions.state)
    print(f"FSM обновлено для пользователя {user_id}, состояние: {PollTaking.answering_questions.state}")
    await send_next_question(message, state)


async def send_next_question(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    user_data = user_poll_state[user_id]
    current_q_index = user_data["current_q"]
    questions = user_data["questions"]

    print(f"send_next_question: {user_id}, current_q_index={current_q_index}, total_questions={len(questions)}")  # Отладка

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

    if text == "✍️ Свой вариант":
        await message.answer("Напишите свой вариант ответа:")
        return

    user_data["answers"].append((question.id, text))
    user_data["current_q"] += 1
    await send_next_question(message, state)

from aiogram import types
from aiogram.dispatcher import FSMContext
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from sqlalchemy.future import select

from database import AsyncSessionLocal
from models import User, UserPollProgress, UserAnswer

# предполагается, что user_poll_state — ваш глобальный dict
# { tg_id: { "poll_id": ..., "answers": [(question_id, text), …] } }
async def finish_poll(message: types.Message, state: FSMContext):
    tg_id = message.from_user.id
    user_data = user_poll_state.get(tg_id)

    if not user_data:
        print(f"finish_poll: нет данных для пользователя {tg_id}")
        return

    async with AsyncSessionLocal() as session:
        result = await session.execute(select(User).where(User.tg_id == tg_id))
        db_user = result.scalar()
        if not db_user:
            await message.answer("❌ Ошибка: пользователь не найден в базе.")
            return
        db_user_id = db_user.id

        progress = UserPollProgress(user_id=db_user_id, poll_id=user_data["poll_id"], is_completed=True)
        session.add(progress)

        for question_id, answer_text in user_data["answers"]:
            ua = UserAnswer(user_id=db_user_id, question_id=question_id, answer_text=answer_text)
            session.add(ua)

        try:
            await session.commit()
            print(f"✅ Данные опроса сохранены для пользователя {tg_id} (db_id={db_user_id})")
        except Exception as e:
            await session.rollback()
            print(f"❌ Ошибка при сохранении опроса: {e}")
            await message.answer("⚠️ Ошибка при сохранении результатов.")
            return

    await message.answer("✅ Опрос завершён. Спасибо за участие!", reply_markup=ReplyKeyboardRemove())

    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(KeyboardButton("📋 Пройти опрос"))
    await message.answer("Выберите действие:", reply_markup=kb)

    await state.finish()
    user_poll_state.pop(tg_id, None)
    print(f"FSM и временное состояние очищены для пользователя {tg_id}")

