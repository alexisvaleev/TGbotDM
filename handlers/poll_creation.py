from aiogram import types, Dispatcher
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.dispatcher import FSMContext
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from database import AsyncSessionLocal
from models import User, Poll, Question, Answer
from sqlalchemy.future import select


class PollCreation(StatesGroup):
    waiting_for_title = State()
    waiting_for_target = State()
    waiting_for_question_text = State()
    waiting_for_answer_options = State()
    waiting_for_more_questions = State()


# Временное хранилище вопросов и вариантов (по user_id)
poll_creation_buffer = {}


async def start_poll_creation(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(User).where(User.tg_id == user_id))
        user = result.scalar()
        if user.role not in ("admin", "teacher"):
            return await message.answer("⛔ У вас нет прав для создания опросов.")

    await state.set_state(PollCreation.waiting_for_title.state)
    await message.answer("Введите заголовок опроса:", reply_markup=ReplyKeyboardRemove())


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
    poll_creation_buffer[message.from_user.id] = []
    await state.set_state(PollCreation.waiting_for_question_text.state)
    await message.answer("Введите текст первого вопроса:", reply_markup=ReplyKeyboardRemove())


async def process_question_text(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    poll_creation_buffer.setdefault(user_id, [])
    poll_creation_buffer[user_id].append({'text': message.text, 'answers': []})
    await state.set_state(PollCreation.waiting_for_answer_options.state)

    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(KeyboardButton("✅ Готово"), KeyboardButton("❌ Нет вариантов"))
    await message.answer(
        "Добавим варианты ответа? Отправляйте варианты по одному сообщению.\n"
        "Когда закончите — нажмите \"✅ Готово\".\n"
        "Если вариантов нет — нажмите \"❌ Нет вариантов\".",
        reply_markup=kb
    )


async def process_answer_options(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    last_question = poll_creation_buffer[user_id][-1]

    if message.text == "✅ Готово":
        await state.set_state(PollCreation.waiting_for_more_questions.state)
        kb = ReplyKeyboardMarkup(resize_keyboard=True)
        kb.add(KeyboardButton("➕ Добавить вопрос"), KeyboardButton("✅ Завершить опрос"))
        await message.answer("Варианты сохранены. Хотите добавить ещё вопрос?", reply_markup=kb)
        return

    if message.text == "❌ Нет вариантов":
        await state.set_state(PollCreation.waiting_for_more_questions.state)
        kb = ReplyKeyboardMarkup(resize_keyboard=True)
        kb.add(KeyboardButton("➕ Добавить вопрос"), KeyboardButton("✅ Завершить опрос"))
        await message.answer("Вопрос сохранён без вариантов. Хотите добавить ещё вопрос?", reply_markup=kb)
        return

    # Добавляем вариант ответа
    last_question['answers'].append(message.text.strip())
    await message.answer(f"Вариант добавлен: {message.text.strip()}")


async def process_more_questions(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    print(f"process_more_questions triggered by user {user_id} with text: {message.text}")

    if message.text == "➕ Добавить вопрос":
        print("Переходим к вводу следующего вопроса")
        await state.set_state(PollCreation.waiting_for_question_text.state)
        await message.answer("Введите текст следующего вопроса:", reply_markup=ReplyKeyboardRemove())
        return

    elif message.text == "✅ Завершить опрос":
        print("Начинаем сохранение опроса")
        data = await state.get_data()
        questions = poll_creation_buffer.get(user_id)

        if not questions:
            print("Ошибка: нет вопросов для сохранения")
            await message.answer("⛔ Вы не добавили ни одного вопроса.")
            return

        try:
            async with AsyncSessionLocal() as session:
                poll = Poll(
                    title=data['title'],
                    target_role=data['target'],
                    group_id=None,
                    created_by=user_id
                )
                session.add(poll)
                await session.commit()
                await session.refresh(poll)
                print(f"Создан опрос с ID {poll.id}")

                for q in questions:
                    question = Question(
                        poll_id=poll.id,
                        question_text=q['text'],
                        question_type='text'  # или 'single_choice', в зависимости от логики
                    )

                    session.add(question)
                    await session.flush()
                    print(f"Добавлен вопрос: {q['text']}")

                    for answer_text in q['answers']:
                        ans = Answer(
                            question_id=question.id,
                            answer_text=answer_text,
                            # selected_options не указываем вовсе
                        )

                await session.commit()
                print("Все вопросы и ответы сохранены")
        except Exception as e:
            print(f"Ошибка при сохранении опроса: {e}")
            await message.answer("⚠️ Произошла ошибка при сохранении опроса. Сообщите разработчику.")
            return

        poll_creation_buffer.pop(user_id, None)

        kb = ReplyKeyboardMarkup(resize_keyboard=True)
        kb.add(KeyboardButton("📊 Статистика"))
        kb.add(KeyboardButton("➕ Создать опрос"), KeyboardButton("🗑 Удалить опрос"))
        kb.add(KeyboardButton("👥 Управление пользователями"))
        await message.answer("✅ Опрос сохранён!", reply_markup=kb)
        await state.finish()
        print("Состояние FSM завершено")
        return

    else:
        print("Неверная команда в процессе создания опроса")
        await message.answer("Пожалуйста, используйте кнопки на клавиатуре.")


def register_poll_creation(dp: Dispatcher):
    dp.register_message_handler(start_poll_creation, text="➕ Создать опрос", state="*")
    dp.register_message_handler(process_poll_title, state=PollCreation.waiting_for_title)
    dp.register_message_handler(process_poll_target, state=PollCreation.waiting_for_target)
    dp.register_message_handler(process_question_text, state=PollCreation.waiting_for_question_text)
    dp.register_message_handler(process_answer_options, state=PollCreation.waiting_for_answer_options)
    dp.register_message_handler(process_more_questions, state=PollCreation.waiting_for_more_questions)
