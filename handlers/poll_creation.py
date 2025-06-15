# handlers/poll_creation.py

import io
from aiogram import types, Dispatcher
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove

from database import AsyncSessionLocal
from handlers.common import BACK, BACK_BTN
from handlers.back import return_to_main_menu
from models import User, Poll, Question, Answer

class PollCreation(StatesGroup):
    waiting_for_title          = State()
    waiting_for_target         = State()
    waiting_for_question_text  = State()
    waiting_for_answer_options = State()
    waiting_for_more_questions = State()

# временный буфер {tg_id: [ { "text": ..., "answers": [...] }, ... ] }
poll_creation_buffer: dict[int, list[dict]] = {}

async def start_poll_creation(message: types.Message, state: FSMContext):
    """Шаг 1. Админ или преподаватель запускает создание."""
    await state.finish()
    tg = message.from_user.id

    async with AsyncSessionLocal() as s:
        user = (await s.execute(
            select(User).where(User.tg_id == tg)
        )).scalar_one_or_none()
    if not user or user.role not in ("admin", "teacher"):
        return await message.answer("⛔ У вас нет прав для создания опросов.")

    await state.set_state(PollCreation.waiting_for_title)
    await message.answer("Введите заголовок опроса:", reply_markup=ReplyKeyboardRemove())


async def process_poll_title(message: types.Message, state: FSMContext):
    """Шаг 2. Сохраняем заголовок и спрашиваем аудиторию."""
    title = message.text.strip()
    await state.update_data(title=title)

    kb = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    kb.add(KeyboardButton("студенты"), KeyboardButton("учителя"), KeyboardButton("все"))
    kb.add(BACK_BTN)

    await state.set_state(PollCreation.waiting_for_target)
    await message.answer("Для кого предназначен опрос?", reply_markup=kb)


async def process_poll_target(message: types.Message, state: FSMContext):
    """Шаг 3. Сохраняем target_role и переходим к первому вопросу."""
    txt = message.text.strip().lower()
    mapping = {
        "студенты": "student",
        "учителя": "teacher",
        "все":      "all"
    }
    if txt not in mapping:
        return await message.answer("⛔ Пожалуйста, выберите вариант кнопками.")

    # сохраняем константу в FSM
    await state.update_data(target_role=mapping[txt])
    poll_creation_buffer[message.from_user.id] = []

    await state.set_state(PollCreation.waiting_for_question_text)
    await message.answer("Введите текст первого вопроса:", reply_markup=ReplyKeyboardRemove())


async def process_question_text(message: types.Message, state: FSMContext):
    """Шаг 4. Сохраняем текст вопроса и предлагаем добавить варианты."""
    uid = message.from_user.id
    buf = poll_creation_buffer.setdefault(uid, [])
    buf.append({"text": message.text.strip(), "answers": []})

    kb = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    kb.add(KeyboardButton("✅ Готово"), KeyboardButton("❌ Нет вариантов"))
    kb.add(BACK_BTN)

    await state.set_state(PollCreation.waiting_for_answer_options)
    await message.answer(
        "Добавьте варианты ответа по одному сообщению.\n"
        "Если готовы — нажмите ✅ Готово.\n"
        "Если вариантов нет — нажмите ❌ Нет вариантов.",
        reply_markup=kb
    )


async def process_answer_options(message: types.Message, state: FSMContext):
    """Шаг 5. Собираем варианты или переходим дальше."""
    uid  = message.from_user.id
    text = message.text.strip()
    buf  = poll_creation_buffer.get(uid, [])
    last = buf[-1]

    if text in ("✅ Готово", "❌ Нет вариантов"):
        kb = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        kb.add(KeyboardButton("➕ Добавить вопрос"), KeyboardButton("✅ Завершить опрос"))
        kb.add(BACK_BTN)

        await state.set_state(PollCreation.waiting_for_more_questions)
        msg = "Варианты сохранены." if text == "✅ Готово" else "Вопрос без вариантов."
        return await message.answer(msg, reply_markup=kb)

    # сохраняем вариант
    last["answers"].append(text)
    return await message.answer(f"Добавлен вариант: {text}")


async def process_more_questions(message: types.Message, state: FSMContext):
    """Шаг 6. Добавить еще вопрос или завершить и сохранить."""
    uid = message.from_user.id
    cmd = message.text.strip()

    # Назад — отмена
    if cmd == BACK:
        poll_creation_buffer.pop(uid, None)
        await state.finish()
        return await return_to_main_menu(message)

    # Добавить вопрос
    if cmd == "➕ Добавить вопрос":
        await state.set_state(PollCreation.waiting_for_question_text)
        return await message.answer("Введите текст следующего вопроса:", reply_markup=ReplyKeyboardRemove())

    # Завершить
    if cmd == "✅ Завершить опрос":
        data = await state.get_data()
        questions = poll_creation_buffer.get(uid, [])
        if not questions:
            return await message.answer("⛔ Нет ни одного вопроса. Добавьте хотя бы один.")

        # Сохраняем Poll, Question и Answer в БД
        async with AsyncSessionLocal() as s:
            poll = Poll(
                title=data["title"],
                target_role=data["target_role"],
                group_id=None,
                created_by=uid
            )
            s.add(poll)
            await s.commit()
            await s.refresh(poll)

            for q in questions:
                q_type = "single_choice" if q["answers"] else "text"
                question = Question(
                    poll_id=poll.id,
                    question_text=q["text"],
                    question_type=q_type
                )
                s.add(question)
                await s.flush()
                for ans_text in q["answers"]:
                    s.add(Answer(question_id=question.id, answer_text=ans_text))
            await s.commit()

        poll_creation_buffer.pop(uid, None)
        await state.finish()
        await message.answer("✅ Опрос сохранён!", reply_markup=ReplyKeyboardRemove())
        return await return_to_main_menu(message)

    # Неизвестная команда
    return await message.answer("Пожалуйста, используйте кнопки на клавиатуре.")


def register_poll_creation(dp: Dispatcher):
    dp.register_message_handler(start_poll_creation, text="➕ Создать опрос", state="*")
    dp.register_message_handler(process_poll_title,   state=PollCreation.waiting_for_title)
    dp.register_message_handler(process_poll_target,  state=PollCreation.waiting_for_target)
    dp.register_message_handler(process_question_text, state=PollCreation.waiting_for_question_text)
    dp.register_message_handler(process_answer_options, state=PollCreation.waiting_for_answer_options)
    dp.register_message_handler(process_more_questions, state=PollCreation.waiting_for_more_questions)

    # Обработка «Назад» на любом шаге PollCreation
    dp.register_message_handler(
        lambda msg, state: return_to_main_menu(msg),
        text=BACK,
        state=[
            PollCreation.waiting_for_title,
            PollCreation.waiting_for_target,
            PollCreation.waiting_for_question_text,
            PollCreation.waiting_for_answer_options,
            PollCreation.waiting_for_more_questions
        ]
    )
