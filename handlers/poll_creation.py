# handlers/poll_creation.py

from aiogram import types, Dispatcher
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.dispatcher import FSMContext
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from sqlalchemy.future import select

from database import AsyncSessionLocal
from models import User, Poll, Question, Answer
from handlers.start import _send_main_menu  # для отображения админ-меню после создания

class PollCreation(StatesGroup):
    waiting_for_title            = State()
    waiting_for_target           = State()
    waiting_for_question_text    = State()
    waiting_for_answer_options   = State()
    waiting_for_more_questions   = State()


# Временное хранилище вопросов и их вариантов (по user_id)
poll_creation_buffer: dict[int, list[dict]] = {}


async def start_poll_creation(message: types.Message, state: FSMContext):
    tg = message.from_user.id
    async with AsyncSessionLocal() as s:
        user = (await s.execute(select(User).where(User.tg_id == tg))).scalar()
    if not user or user.role not in ("admin", "teacher"):
        return await message.answer("⛔ У вас нет прав для создания опросов.")

    await state.set_state(PollCreation.waiting_for_title)
    await message.answer("Введите заголовок опроса:", reply_markup=ReplyKeyboardRemove())


async def process_poll_title(message: types.Message, state: FSMContext):
    await state.update_data(title=message.text.strip())
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(KeyboardButton("студенты"), KeyboardButton("учителя"), KeyboardButton("все"))
    await state.set_state(PollCreation.waiting_for_target)
    await message.answer("Для кого предназначен опрос?", reply_markup=kb)


async def process_poll_target(message: types.Message, state: FSMContext):
    target = message.text.lower().strip()
    if target not in ("студенты", "учителя", "все"):
        return await message.answer("⛔ Пожалуйста, выберите один из вариантов кнопками.")
    await state.update_data(target=target)
    poll_creation_buffer[message.from_user.id] = []
    await state.set_state(PollCreation.waiting_for_question_text)
    await message.answer("Введите текст первого вопроса:", reply_markup=ReplyKeyboardRemove())


async def process_question_text(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    poll_creation_buffer.setdefault(uid, []).append({
        "text": message.text.strip(),
        "answers": []
    })
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(KeyboardButton("✅ Готово"), KeyboardButton("❌ Нет вариантов"))
    await state.set_state(PollCreation.waiting_for_answer_options)
    await message.answer(
        "Добавьте варианты ответа по одному сообщению.\n"
        "Когда закончите — нажмите ✅ Готово.\n"
        "Если вариантов нет — нажмите ❌ Нет вариантов.",
        reply_markup=kb
    )


async def process_answer_options(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    buf = poll_creation_buffer[uid]
    last_q = buf[-1]
    text = message.text.strip()

    if text == "✅ Готово" or text == "❌ Нет вариантов":
        kb = ReplyKeyboardMarkup(resize_keyboard=True)
        kb.add(KeyboardButton("➕ Добавить вопрос"), KeyboardButton("✅ Завершить опрос"))
        await state.set_state(PollCreation.waiting_for_more_questions)
        return await message.answer(
            "Варианты сохранены." if text == "✅ Готово" else "Вопрос сохранён без вариантов.",
            reply_markup=kb
        )

    # добавляем новый вариант
    last_q["answers"].append(text)
    return await message.answer(f"Вариант добавлен: {text}")


async def process_more_questions(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    cmd = message.text.strip()

    if cmd == "➕ Добавить вопрос":
        await state.set_state(PollCreation.waiting_for_question_text)
        return await message.answer("Введите текст следующего вопроса:", reply_markup=ReplyKeyboardRemove())

    if cmd == "✅ Завершить опрос":
        data = await state.get_data()
        questions = poll_creation_buffer.get(uid, [])
        if not questions:
            return await message.answer("⛔ Вы не добавили ни одного вопроса.")

        # Сохраняем опрос, вопросы и варианты в БД
        async with AsyncSessionLocal() as session:
            poll = Poll(
                title=data["title"],
                target_role=data["target"],
                group_id=None,
                created_by=uid
            )
            session.add(poll)
            await session.commit()
            await session.refresh(poll)

            for q in questions:
                has_opts = bool(q["answers"])
                q_type = "single_choice" if has_opts else "text"
                question = Question(
                    poll_id=poll.id,
                    question_text=q["text"],
                    question_type=q_type
                )
                session.add(question)
                await session.flush()  # получить question.id

                for ans_text in q["answers"]:
                    answer = Answer(
                        question_id=question.id,
                        answer_text=ans_text
                    )
                    session.add(answer)

            await session.commit()

        # Очистка буфера и завершение FSM
        poll_creation_buffer.pop(uid, None)
        await state.finish()

        # Убираем клавиатуру и показываем админ-меню
        await message.answer("✅ Опрос сохранён!", reply_markup=ReplyKeyboardRemove())
        return await _send_main_menu(message, role="admin")

    # Прочие сообщения не обрабатываем
    return await message.answer("Пожалуйста, используйте кнопки на клавиатуре.")


def register_poll_creation(dp: Dispatcher):
    dp.register_message_handler(start_poll_creation, text="➕ Создать опрос", state="*")
    dp.register_message_handler(process_poll_title,   state=PollCreation.waiting_for_title)
    dp.register_message_handler(process_poll_target,  state=PollCreation.waiting_for_target)
    dp.register_message_handler(process_question_text, state=PollCreation.waiting_for_question_text)
    dp.register_message_handler(process_answer_options, state=PollCreation.waiting_for_answer_options)
    dp.register_message_handler(process_more_questions, state=PollCreation.waiting_for_more_questions)
