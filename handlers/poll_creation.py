# handlers/poll_creation.py

from aiogram import types, Dispatcher
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.types import (
    ReplyKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardRemove
)
from sqlalchemy.future import select

from database import AsyncSessionLocal
from models import User, Poll, Question, Answer
from handlers.back import return_to_main_menu
from handlers.common import BACK, BACK_BTN

class PollCreation(StatesGroup):
    waiting_for_title          = State()
    waiting_for_target         = State()
    waiting_for_question_text  = State()
    waiting_for_answer_options = State()
    waiting_for_more_questions = State()

# временный буфер {tg_id: [ { "text": str, "answers": [str,...] }, ... ]}
poll_creation_buffer: dict[int, list[dict]] = {}

async def start_poll_creation(message: types.Message, state: FSMContext):
    await state.finish()
    tg = message.from_user.id

    # проверяем права
    async with AsyncSessionLocal() as s:
        me = (await s.execute(
            select(User).where(User.tg_id == tg)
        )).scalar_one_or_none()
    if not me or me.role not in ("admin", "teacher"):
        return await message.answer("⛔ У вас нет прав для создания опросов.")

    # шаг 1: спрашиваем заголовок
    await PollCreation.waiting_for_title.set()
    await message.answer(
        "Введите заголовок опроса:",
        reply_markup=ReplyKeyboardRemove()
    )


async def process_poll_title(message: types.Message, state: FSMContext):
    txt = message.text.strip()
    # BACK?
    if txt == BACK:
        await state.finish()
        return await return_to_main_menu(message)

    # валидный title
    await state.update_data(title=txt)

    kb = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    kb.add(KeyboardButton("студенты"), KeyboardButton("учителя"), KeyboardButton("все"))
    kb.add(BACK_BTN)

    await PollCreation.waiting_for_target.set()
    await message.answer("Для кого предназначен опрос?", reply_markup=kb)


async def process_poll_target(message: types.Message, state: FSMContext):
    txt = message.text.strip().lower()
    tg = message.from_user.id

    # BACK?
    if txt == BACK.lower():
        poll_creation_buffer.pop(tg, None)
        await state.finish()
        return await return_to_main_menu(message)

    mapping = {"студенты": "student", "учителя": "teacher", "все": "all"}
    if txt not in mapping:
        # остаёмся в том же шаге, показываем повторно клавиатуру
        kb = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        kb.add(KeyboardButton("студенты"), KeyboardButton("учителя"), KeyboardButton("все"))
        kb.add(BACK_BTN)
        return await message.answer("⛔ Выберите вариант кнопками.", reply_markup=kb)

    # принятый target
    await state.update_data(target_role=mapping[txt])
    poll_creation_buffer[tg] = []

    await PollCreation.waiting_for_question_text.set()
    await message.answer("Введите текст первого вопроса:", reply_markup=ReplyKeyboardRemove())


async def process_question_text(message: types.Message, state: FSMContext):
    txt = message.text.strip()
    tg  = message.from_user.id

    # BACK?
    if txt == BACK:
        poll_creation_buffer.pop(tg, None)
        await state.finish()
        return await return_to_main_menu(message)

    buf = poll_creation_buffer.setdefault(tg, [])
    buf.append({"text": txt, "answers": []})

    kb = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    kb.add(KeyboardButton("✅ Готово"), KeyboardButton("❌ Нет вариантов"))
    kb.add(BACK_BTN)

    await PollCreation.waiting_for_answer_options.set()
    await message.answer(
        "Добавьте варианты ответа по одному сообщению.\n"
        "Когда закончите — ✅ Готово.\n"
        "Если вариантов нет — ❌ Нет вариантов.",
        reply_markup=kb
    )


async def process_answer_options(message: types.Message, state: FSMContext):
    txt = message.text.strip()
    tg  = message.from_user.id

    # BACK?
    if txt == BACK:
        poll_creation_buffer.pop(tg, None)
        await state.finish()
        return await return_to_main_menu(message)

    buf = poll_creation_buffer.get(tg, [])
    last = buf[-1]

    # закончили сбор вариантов?
    if txt in ("✅ Готово", "❌ Нет вариантов"):
        kb = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        kb.add(KeyboardButton("➕ Добавить вопрос"), KeyboardButton("✅ Завершить опрос"))
        kb.add(BACK_BTN)

        await PollCreation.waiting_for_more_questions.set()
        note = "Варианты сохранены." if txt == "✅ Готово" else "Вопрос без вариантов."
        return await message.answer(note, reply_markup=kb)

    # добавляем вариант
    last["answers"].append(txt)
    return await message.answer(f"Добавлен вариант: {txt}")


async def process_more_questions(message: types.Message, state: FSMContext):
    txt = message.text.strip()
    tg  = message.from_user.id

    # BACK?
    if txt == BACK:
        poll_creation_buffer.pop(tg, None)
        await state.finish()
        return await return_to_main_menu(message)

    if txt == "➕ Добавить вопрос":
        await PollCreation.waiting_for_question_text.set()
        return await message.answer("Введите текст следующего вопроса:", reply_markup=ReplyKeyboardRemove())

    if txt == "✅ Завершить опрос":
        data = await state.get_data()
        questions = poll_creation_buffer.get(tg, [])
        if not questions:
            return await message.answer("⛔ Добавьте хотя бы один вопрос.")

        # сохраняем всё в БД
        async with AsyncSessionLocal() as s:
            poll = Poll(
                title=data["title"],
                target_role=data["target_role"],
                group_id=None,
                created_by=tg
            )
            s.add(poll)
            await s.commit()
            await s.refresh(poll)

            for q in questions:
                qtype = "single_choice" if q["answers"] else "text"
                q_obj = Question(
                    poll_id=poll.id,
                    question_text=q["text"],
                    question_type=qtype
                )
                s.add(q_obj)
                await s.flush()
                for ans in q["answers"]:
                    s.add(Answer(question_id=q_obj.id, answer_text=ans))
            await s.commit()

        poll_creation_buffer.pop(tg, None)
        await state.finish()
        await message.answer("✅ Опрос сохранён!", reply_markup=ReplyKeyboardRemove())
        return await return_to_main_menu(message)

    # нераспознанная команда
    return await message.answer("Пожалуйста, используйте кнопки на клавиатуре.")


def register_poll_creation(dp: Dispatcher):
    dp.register_message_handler(start_poll_creation, text="➕ Создать опрос", state="*")
    dp.register_message_handler(process_poll_title, state=PollCreation.waiting_for_title)
    dp.register_message_handler(process_poll_target, state=PollCreation.waiting_for_target)
    dp.register_message_handler(process_question_text, state=PollCreation.waiting_for_question_text)
    dp.register_message_handler(process_answer_options, state=PollCreation.waiting_for_answer_options)
    dp.register_message_handler(process_more_questions, state=PollCreation.waiting_for_more_questions)
