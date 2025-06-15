# handlers/poll_take.py

import logging
from aiogram import types, Dispatcher
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from sqlalchemy import update, or_
from sqlalchemy.future import select

from database import AsyncSessionLocal
from handlers.common import BACK_BTN
from handlers.back import return_to_main_menu
from models import (
    User, Poll, Question, Answer,
    UserAnswer, UserPollProgress
)

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


class PollTaking(StatesGroup):
    choosing_poll       = State()
    answering_questions = State()


async def start_poll_taking(message: types.Message, state: FSMContext):
    await state.finish()
    tg = message.from_user.id
    await message.answer("🔍 Ищем доступные опросы…", reply_markup=ReplyKeyboardRemove())

    # 1) Загрузка пользователя
    async with AsyncSessionLocal() as s:
        user = (await s.execute(
            select(User).where(User.tg_id == tg)
        )).scalar_one_or_none()

    if not user or user.role not in ("student", "teacher"):
        return await message.answer("⛔ У вас нет доступа к опросам.")

    # 2) Какие опросы уже завершены
    async with AsyncSessionLocal() as s:
        done = (await s.execute(
            select(UserPollProgress.poll_id)
            .where(
                UserPollProgress.user_id == user.id,
                UserPollProgress.is_completed.is_(True)
            )
        )).scalars().all()

    # 3) Формируем перечень разрешённых ролей-мишеней
    rus_map = {"student": "студенты", "teacher": "учителя"}
    allowed = {
        user.role,        # english
        rus_map.get(user.role),  # russian
        "all",            # new english
        "все"             # old russian
    }
    allowed.discard(None)

    # 4) Загружаем все подходящие непроходённые опросы
    async with AsyncSessionLocal() as s:
        polls = (await s.execute(
            select(Poll)
            .where(
                Poll.target_role.in_(allowed),
                or_(
                    Poll.group_id.is_(None),
                    Poll.group_id == user.group_id
                )
            )
        )).scalars().all()

    # Убираем уже завершённые
    polls = [p for p in polls if p.id not in done]

    logger.debug("User %s role=%s, group=%s", tg, user.role, user.group_id)
    logger.debug("Allowed roles: %r", allowed)
    logger.debug("Found polls (before dedupe): %r", [(p.id,p.title,p.target_role) for p in polls])

    if not polls:
        return await message.answer("❌ Нет доступных опросов.", reply_markup=BACK_BTN)

    # 5) Пропишем кнопки
    kb = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    for idx, p in enumerate(polls, start=1):
        kb.add(KeyboardButton(f"{idx}. {p.title}"))
    kb.add(BACK_BTN)

    await state.update_data(poll_ids=[p.id for p in polls])
    await PollTaking.choosing_poll.set()
    await message.answer("📋 Выберите опрос:", reply_markup=kb)


async def choose_poll(message: types.Message, state: FSMContext):
    text = message.text.strip()
    if text == BACK_BTN:
        await state.finish()
        return await return_to_main_menu(message)

    data = await state.get_data()
    ids = data.get("poll_ids", [])
    parts = text.split(".")
    if not parts[0].isdigit():
        return await message.answer("Нажмите кнопку с номером.")
    idx = int(parts[0]) - 1
    if idx < 0 or idx >= len(ids):
        return await message.answer("Неверный номер.")

    poll_id = ids[idx]
    tg = message.from_user.id

    # заводим progress и подгружаем вопросы
    async with AsyncSessionLocal() as s:
        user = (await s.execute(
            select(User).where(User.tg_id == tg)
        )).scalar_one()
        prog = UserPollProgress(user_id=user.id, poll_id=poll_id)
        s.add(prog)
        await s.commit()
        await s.refresh(prog)

        q_objs = (await s.execute(
            select(Question)
            .where(Question.poll_id == poll_id)
            .order_by(Question.id)
        )).scalars().all()

    await state.update_data(
        progress_id=prog.id,
        question_ids=[q.id for q in q_objs],
        q_index=0
    )
    await PollTaking.answering_questions.set()
    return await _ask_question(message, state)


async def _ask_question(message: types.Message, state: FSMContext):
    data = await state.get_data()
    idx = data["q_index"]
    q_ids = data["question_ids"]

    # закончились?
    if idx >= len(q_ids):
        return await _finish_poll(message, state)

    q_id = q_ids[idx]
    async with AsyncSessionLocal() as s:
        q_obj = (await s.execute(
            select(Question).where(Question.id == q_id)
        )).scalar_one()
        opts = (await s.execute(
            select(Answer).where(Answer.question_id == q_id)
        )).scalars().all()

    # если есть варианты — клавиатура
    if opts:
        kb = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        for o in opts:
            kb.add(KeyboardButton(o.answer_text))
        kb.add(BACK_BTN)
        await message.answer(f"❓ {q_obj.question_text}", reply_markup=kb)
    else:
        await message.answer(f"❓ {q_obj.question_text}", reply_markup=ReplyKeyboardRemove())


async def process_answer(message: types.Message, state: FSMContext):
    text = message.text.strip()
    data = await state.get_data()
    idx = data["q_index"]
    q_id = data["question_ids"][idx]
    prog_id = data["progress_id"]

    if text == BACK_BTN:
        await state.finish()
        return await return_to_main_menu(message)

    # проверяем, есть ли варианты вообще
    async with AsyncSessionLocal() as s:
        has_opts = (await s.execute(
            select(Answer).where(Answer.question_id == q_id)
        )).first()

    if has_opts:
        # только кнопочные ответы
        valid_opts = {a.answer_text for a in (await AsyncSessionLocal()
                                               .execute(select(Answer)
                                                        .where(Answer.question_id == q_id))
                                               ).scalars().all()}
        if text not in valid_opts:
            return await message.answer("Пожалуйста, выберите вариант кнопкой.")

    # сохраняем любой текстовый или кнопочный ответ
    async with AsyncSessionLocal() as s:
        ua = UserAnswer(
            user_id=(await s.execute(
                select(User).where(User.tg_id == message.from_user.id)
            )).scalar_one().id,
            question_id=q_id,
            answer_text=text
        )
        s.add(ua)
        await s.execute(
            update(UserPollProgress)
            .where(UserPollProgress.id == prog_id)
            .values(last_question_id=q_id)
        )
        await s.commit()

    await state.update_data(q_index=idx + 1)
    return await _ask_question(message, state)


async def _finish_poll(message: types.Message, state: FSMContext):
    data = await state.get_data()
    prog_id = data["progress_id"]

    async with AsyncSessionLocal() as s:
        await s.execute(
            update(UserPollProgress)
            .where(UserPollProgress.id == prog_id)
            .values(is_completed=True)
        )
        await s.commit()

    await state.finish()
    return await return_to_main_menu(message)


def register_poll_take(dp: Dispatcher):
    dp.register_message_handler(start_poll_taking, text="📋 Пройти опрос", state="*")
    dp.register_message_handler(choose_poll, state=PollTaking.choosing_poll)
    dp.register_message_handler(process_answer, state=PollTaking.answering_questions)
