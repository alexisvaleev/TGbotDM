# handlers.py
from aiogram import Dispatcher, types
from aiogram.dispatcher.filters import CommandStart, Text
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from config import load_config
from database import AsyncSessionLocal
from models import User, Poll, Question, Answer, UserPollProgress, UserAnswer
from sqlalchemy.future import select
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove

config = load_config()

# FSM для создания опроса
class PollCreation(StatesGroup):
    waiting_for_title = State()
    waiting_for_target = State()
    waiting_for_questions = State()

# FSM для прохождения опроса
class PollTaking(StatesGroup):
    choosing_poll = State()
    answering_questions = State()

poll_buffer = {}
user_poll_state = {}

def get_user_keyboard():
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(KeyboardButton("📋 Пройти опрос"))
    return kb

async def cmd_start(message: types.Message, state: FSMContext):
    print("📥 /start от:", message.from_user.id)
    await message.answer(f"Ваш Telegram ID: {message.from_user.id}")
    user_id = message.from_user.id

    async with AsyncSessionLocal() as session:
        result = await session.execute(select(User).where(User.tg_id == user_id))
        user = result.scalar()

        if user:
            await message.answer(f"Привет! Вы вошли как {user.role.capitalize()} ✅")
        else:
            role = "admin" if user_id in config.ADMIN_IDS else "student"
            user = User(tg_id=user_id, role=role)
            session.add(user)
            await session.commit()
            await message.answer(f"Добро пожаловать! Вы зарегистрированы как {role.capitalize()} ✅")

        if user.role == "admin":
            kb = ReplyKeyboardMarkup(resize_keyboard=True)
            kb.add(KeyboardButton("📊 Статистика"))
            kb.add(KeyboardButton("➕ Создать опрос"), KeyboardButton("🗑 Удалить опрос"))
            kb.add(KeyboardButton("👥 Управление пользователями"))
            await message.answer("Выберите действие:", reply_markup=kb)
        else:
            await message.answer("Выберите действие:", reply_markup=get_user_keyboard())

# Хендлер создания опроса
async def start_poll_creation(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(User).where(User.tg_id == user_id))
        user = result.scalar()

        if user.role not in ("admin", "teacher"):
            return await message.answer("⛔ У вас нет прав для создания опросов.")

    await state.set_state(PollCreation.waiting_for_title.state)
    await message.answer("Введите заголовок опроса:")

async def process_poll_title(message: types.Message, state: FSMContext):
    await state.update_data(title=message.text)
    await state.set_state(PollCreation.waiting_for_target.state)

    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(KeyboardButton("студенты"), KeyboardButton("учителя"), KeyboardButton("все"))
    await message.answer("Для кого предназначен опрос?", reply_markup=kb)

async def process_poll_target(message: types.Message, state: FSMContext):
    if message.text.lower() not in ("студенты", "учителя", "все"):
        return await message.answer("⛔ Пожалуйста, выберите из предложенных вариантов.")

    await state.update_data(target=message.text.lower())
    await state.set_state(PollCreation.waiting_for_questions.state)
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(KeyboardButton("✅"))
    await message.answer("Отправляйте вопросы по одному сообщению. Когда закончите — нажмите ✅", reply_markup=kb)

async def process_poll_questions(message: types.Message, state: FSMContext):
    if message.text == "✅":
        data = await state.get_data()
        async with AsyncSessionLocal() as session:
            poll = Poll(title=data['title'], target_role=data['target'])
            session.add(poll)
            await session.commit()
            await session.refresh(poll)

            for q in data.get("questions", []):
                if '|' in q:
                    q_text, raw_answers = q.split('|', 1)
                    question = Question(poll_id=poll.id, text=q_text.strip(), allow_custom=True)
                    session.add(question)
                    await session.flush()
                    for answer_text in raw_answers.split(';'):
                        ans = Answer(question_id=question.id, text=answer_text.strip())
                        session.add(ans)
                else:
                    question = Question(poll_id=poll.id, text=q.strip())
                    session.add(question)
            await session.commit()

        await message.answer("✅ Опрос сохранён!", reply_markup=get_user_keyboard())
        await state.finish()
    else:
        data = await state.get_data()
        questions = data.get("questions", [])
        questions.append(message.text.strip())
        await state.update_data(questions=questions)
        await message.answer(
            "Вопрос добавлен. Можете добавить ещё.\n"
            "💡 Чтобы указать варианты ответа — используйте формат:\n"
            "вопрос|вариант1;вариант2;вариант3\n"
            "Пользователь сможет также ввести свой вариант, если захочет.\n"
            "Когда всё готово — нажмите ✅"
        )

async def start_poll_taking(message: types.Message, state: FSMContext):
    user_id = message.from_user.id

    async with AsyncSessionLocal() as session:
        result = await session.execute(select(User).where(User.tg_id == user_id))
        user = result.scalar()

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

        user_poll_state[user_id] = {"polls": polls}

        await state.set_state(PollTaking.choosing_poll.state)
        await message.answer(text + "\nВведите номер опроса, который хотите пройти:")

async def choose_poll(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    if not message.text.isdigit():
        return await message.answer("Пожалуйста, введите номер из списка.")

    index = int(message.text) - 1
    user_data = user_poll_state.get(user_id)
    if not user_data or index >= len(user_data["polls"]):
        return await message.answer("Некорректный номер опроса.")

    selected_poll = user_data["polls"][index]
    user_data["poll_id"] = selected_poll.id
    user_data["current_q"] = 0

    async with AsyncSessionLocal() as session:
        questions = (await session.execute(
            select(Question).where(Question.poll_id == selected_poll.id)
        )).scalars().all()

        user_data["questions"] = questions
        user_data["answers"] = []

    await state.set_state(PollTaking.answering_questions.state)
    await send_next_question(message, state)

async def send_next_question(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    user_data = user_poll_state[user_id]
    current_q_index = user_data["current_q"]
    questions = user_data["questions"]

    if current_q_index >= len(questions):
        async with AsyncSessionLocal() as session:
            user_result = await session.execute(select(User).where(User.tg_id == user_id))
            user = user_result.scalar()
            progress = UserPollProgress(
                user_id=user.id,
                poll_id=user_data["poll_id"],
                is_completed=True
            )
            session.add(progress)
            for q_id, ans_text in user_data["answers"]:
                session.add(UserAnswer(user_id=user.id, question_id=q_id, answer_text=ans_text))
            await session.commit()

        await message.answer("✅ Опрос завершён. Спасибо!", reply_markup=ReplyKeyboardRemove())
        await state.finish()
        return

    question = questions[current_q_index]
    user_data["current_question"] = question

    async with AsyncSessionLocal() as session:
        answers = (await session.execute(
            select(Answer).where(Answer.question_id == question.id)
        )).scalars().all()

    if answers:
        markup = ReplyKeyboardMarkup(resize_keyboard=True)
        for ans in answers:
            markup.add(KeyboardButton(ans.text))
        if question.allow_custom:
            markup.add(KeyboardButton("✍️ Свой вариант"))
        await message.answer(f"❓ {question.text}", reply_markup=markup)
    else:
        await message.answer(f"❓ {question.text}", reply_markup=ReplyKeyboardRemove())

async def process_answer(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    user_data = user_poll_state[user_id]

def register_handlers(dp: Dispatcher):
    dp.register_message_handler(cmd_start, CommandStart(), state="*")
    dp.register_message_handler(start_poll_creation, Text(equals="➕ Создать опрос"), state="*")
    dp.register_message_handler(process_poll_title, state=PollCreation.waiting_for_title)
    dp.register_message_handler(process_poll_target, state=PollCreation.waiting_for_target)
    dp.register_message_handler(process_poll_questions, state=PollCreation.waiting_for_questions)
    dp.register_message_handler(start_poll_taking, Text(equals="📋 Пройти опрос"), state="*")
    dp.register_message_handler(choose_poll, state=PollTaking.choosing_poll)
    dp.register_message_handler(process_answer, state=PollTaking.answering_questions)

