# handlers/poll_take.py
import logging
from aiogram import types, Dispatcher
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from sqlalchemy import select, update
from handlers.common import BACK_BTN
from database import AsyncSessionLocal
from models import User, Poll, Question, Answer, UserAnswer, UserPollProgress

logging.basicConfig(level=logging.DEBUG)

class PollTaking(StatesGroup):
    choosing_poll       = State()
    answering_questions = State()

async def start_poll_taking(message: types.Message, state: FSMContext):
    await state.finish()
    await message.answer("Ищем доступные опросы…", reply_markup=ReplyKeyboardRemove())
    tg = message.from_user.id

    async with AsyncSessionLocal() as s:
        user = (await s.execute(select(User).where(User.tg_id == tg))).scalar()
    if not user:
        return await message.answer("❌ Сначала /start.")

    async with AsyncSessionLocal() as s:
        polls = (await s.execute(
            select(Poll)
            .where(
                (Poll.target_role == user.role) | (Poll.target_role == "все"),
                (Poll.group_id.is_(None)) | (Poll.group_id == user.group_id)
            )
        )).scalars().all()
    if not polls:
        return await message.answer("❌ Нет опросов.")

    kb = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    for i, p in enumerate(polls, 1):
        kb.add(KeyboardButton(f"{i}. {p.title}"))
    kb.add(BACK_BTN)
    await state.update_data(poll_ids=[p.id for p in polls])
    await PollTaking.choosing_poll.set()
    await message.answer("Выберите опрос:", reply_markup=kb)

async def choose_poll(message: types.Message, state: FSMContext):
    data = await state.get_data()
    ids  = data.get("poll_ids", [])
    part = (message.text or "").split(".")
    if not part[0].isdigit():
        return await message.answer("Нажмите кнопку с номером.")
    idx = int(part[0]) - 1
    if idx < 0 or idx >= len(ids):
        return await message.answer("Неверный номер.")
    poll_id = ids[idx]
    tg = message.from_user.id

    async with AsyncSessionLocal() as s:
        user = (await s.execute(select(User).where(User.tg_id == tg))).scalar()
        prog = UserPollProgress(user_id=user.id, poll_id=poll_id)
        s.add(prog)
        await s.commit()
        await s.refresh(prog)

        q_objs = (await s.execute(select(Question).where(Question.poll_id == poll_id))).scalars().all()
    q_ids = [q.id for q in q_objs]

    logging.debug(f"User {tg} started poll {poll_id}, questions: {len(q_ids)}")
    await state.update_data(progress_id=prog.id, question_ids=q_ids, q_index=0)
    await PollTaking.answering_questions.set()
    await _ask_question(message, state)

async def _ask_question(message: types.Message, state: FSMContext):
    data = await state.get_data()
    q_ids = data["question_ids"]
    idx   = data["q_index"]
    if idx >= len(q_ids):
        return await _finish_poll(message, state)

    q_id = q_ids[idx]
    async with AsyncSessionLocal() as s:
        q_obj   = (await s.execute(select(Question).where(Question.id == q_id))).scalar()
        answers = (await s.execute(select(Answer).where(Answer.question_id == q_id))).scalars().all()

    logging.debug(f"Asking Q#{idx+1}/{len(q_ids)} id={q_id}: '{q_obj.question_text}'")
    logging.debug("Loaded answers: %r", [a.answer_text for a in answers])

    if answers:
        kb = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        for a in answers:
            kb.add(KeyboardButton(a.answer_text))
        kb.add(BACK_BTN)
        await message.answer(f"❓ {q_obj.question_text}", reply_markup=kb)
    else:
        await message.answer(f"❓ {q_obj.question_text}", reply_markup=ReplyKeyboardRemove())

async def process_answer(message: types.Message, state: FSMContext):
    data    = await state.get_data()
    q_ids   = data["question_ids"]
    idx     = data["q_index"]
    prog_id = data["progress_id"]
    text    = message.text.strip()

    # Валидация
    async with AsyncSessionLocal() as s:
        valid = (await s.execute(
            select(Answer).where(
                Answer.question_id == q_ids[idx],
                Answer.answer_text == text
            )
        )).scalar()
    if not valid:
        return await message.answer("Выберите ответ кнопкой.")

    tg = message.from_user.id
    async with AsyncSessionLocal() as s:
        user = (await s.execute(select(User).where(User.tg_id == tg))).scalar()
        s.add(UserAnswer(user_id=user.id,
                         question_id=q_ids[idx],
                         answer_text=text))
        await s.execute(
            update(UserPollProgress)
            .where(UserPollProgress.id == prog_id)
            .values(last_question_id=q_ids[idx])
        )
        await s.commit()

    await state.update_data(q_index=idx+1)
    await _ask_question(message, state)

async def _finish_poll(message: types.Message, state: FSMContext):
    data    = await state.get_data()
    prog_id = data["progress_id"]
    async with AsyncSessionLocal() as s:
        await s.execute(
            update(UserPollProgress)
            .where(UserPollProgress.id == prog_id)
            .values(is_completed=True)
        )
        await s.commit()
    await message.answer("🎉 Готово!", reply_markup=ReplyKeyboardRemove())
    await state.finish()

def register_poll_take(dp: Dispatcher):
    dp.register_message_handler(start_poll_taking, text="📋 Пройти опрос", state="*")
    dp.register_message_handler(choose_poll, state=PollTaking.choosing_poll)
    dp.register_message_handler(process_answer, state=PollTaking.answering_questions)
