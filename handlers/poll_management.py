# handlers/poll_management.py

import io
import csv
from aiogram import types, Dispatcher
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.types import (
    ReplyKeyboardRemove,
    ReplyKeyboardMarkup,
    KeyboardButton,
    InputFile
)
from sqlalchemy.future import select
from sqlalchemy import delete, update

from database import AsyncSessionLocal
from models import (
    User,
    Poll,
    Question,
    Answer,
    UserPollProgress,
    UserAnswer
)
from handlers.common import BACK_BTN
from handlers.back import return_to_main_menu


class DeletePollStates(StatesGroup):
    choosing   = State()
    confirming = State()


class ExportPollStates(StatesGroup):
    choosing = State()


# ——— Удаление опроса ——————————————————————————————————————————

async def start_delete_poll(message: types.Message, state: FSMContext):
    tg_id = message.from_user.id
    async with AsyncSessionLocal() as session:
        me = (await session.execute(
            select(User).where(User.tg_id == tg_id)
        )).scalar_one_or_none()
    if not me or me.role not in ("admin", "teacher"):
        return await message.answer("⛔ Только админ или преподаватель может удалять опросы.")

    async with AsyncSessionLocal() as session:
        polls = (await session.execute(select(Poll))).scalars().all()
    if not polls:
        return await message.answer("Нет опросов для удаления.", reply_markup=BACK_BTN)

    await state.update_data(poll_ids=[p.id for p in polls])
    text = "🗑 Выберите опрос для удаления:\n" + "\n".join(
        f"{i+1}. {p.title}" for i, p in enumerate(polls)
    )
    await DeletePollStates.choosing.set()
    await message.answer(text, reply_markup=ReplyKeyboardRemove())


async def choose_delete_poll(message: types.Message, state: FSMContext):
    data = await state.get_data()
    poll_ids = data.get("poll_ids", [])
    txt = message.text.strip()
    if not txt.isdigit():
        return await message.answer("Введите номер опроса.")
    idx = int(txt) - 1
    if idx < 0 or idx >= len(poll_ids):
        return await message.answer("Неверный номер опроса.")
    await state.update_data(chosen_id=poll_ids[idx])

    kb = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    kb.add(KeyboardButton("✅ Да"), KeyboardButton("❌ Нет"))
    await DeletePollStates.confirming.set()
    await message.answer("⚠️ Подтвердите удаление опроса:", reply_markup=kb)


async def confirm_delete_poll(message: types.Message, state: FSMContext):
    txt = message.text.strip()
    data = await state.get_data()
    poll_id = data.get("chosen_id")

    if txt != "✅ Да":
        await message.answer("❌ Удаление отменено.", reply_markup=ReplyKeyboardRemove())
        await state.finish()
        return await return_to_main_menu(message)

    async with AsyncSessionLocal() as session:
        try:
            await session.execute(
                update(UserPollProgress)
                .where(UserPollProgress.poll_id == poll_id)
                .values(last_question_id=None)
            )
            await session.execute(
                delete(UserPollProgress).where(UserPollProgress.poll_id == poll_id)
            )
            q_res = await session.execute(
                select(Question.id).where(Question.poll_id == poll_id)
            )
            question_ids = [q_id for (q_id,) in q_res.all()]

            if question_ids:
                await session.execute(
                    delete(UserAnswer).where(UserAnswer.question_id.in_(question_ids))
                )
                await session.execute(
                    delete(Answer).where(Answer.question_id.in_(question_ids))
                )
                await session.execute(
                    delete(Question).where(Question.id.in_(question_ids))
                )

            await session.execute(
                delete(Poll).where(Poll.id == poll_id)
            )
            await session.commit()
            await message.answer("✅ Опрос удалён.", reply_markup=ReplyKeyboardRemove())
        except Exception as e:
            await session.rollback()
            await message.answer(f"⚠️ Ошибка при удалении: {e}", reply_markup=ReplyKeyboardRemove())

    await state.finish()
    return await return_to_main_menu(message)


# ——— Экспорт результатов ——————————————————————————————————————————

async def start_export_poll(message: types.Message, state: FSMContext):
    tg_id = message.from_user.id
    async with AsyncSessionLocal() as session:
        me = (await session.execute(
            select(User).where(User.tg_id == tg_id)
        )).scalar_one_or_none()
    # разрешаем и admin, и teacher
    if not me or me.role not in ("admin", "teacher"):
        return await message.answer("⛔ Только админ или преподаватель может экспортировать результаты.")

    async with AsyncSessionLocal() as session:
        polls = (await session.execute(select(Poll))).scalars().all()
    if not polls:
        return await message.answer("Нет опросов для экспорта.", reply_markup=BACK_BTN)

    await state.update_data(poll_ids=[p.id for p in polls])
    text = "📥 Выберите опрос для экспорта:\n" + "\n".join(
        f"{i+1}. {p.title}" for i, p in enumerate(polls)
    )
    await ExportPollStates.choosing.set()
    await message.answer(text, reply_markup=ReplyKeyboardRemove())


async def choose_export_poll(message: types.Message, state: FSMContext):
    data = await state.get_data()
    poll_ids = data.get("poll_ids", [])
    txt = message.text.strip()
    if not txt.isdigit():
        return await message.answer("Введите номер опроса.")
    idx = int(txt) - 1
    if idx < 0 or idx >= len(poll_ids):
        return await message.answer("Неверный номер опроса.")
    poll_id = poll_ids[idx]

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["question_id", "question_text", "user_tg_id", "answer_text"])

    async with AsyncSessionLocal() as session:
        questions = (await session.execute(
            select(Question).where(Question.poll_id == poll_id)
        )).scalars().all()

        for q in questions:
            rows = (await session.execute(
                select(UserAnswer, User.tg_id)
                .join(User, User.id == UserAnswer.user_id)
                .where(UserAnswer.question_id == q.id)
            )).all()
            for ua, tg in rows:
                writer.writerow([
                    q.id,
                    q.question_text,
                    tg,
                    ua.answer_text
                ])

    output.seek(0)
    data_bytes = output.getvalue().encode("utf-8")
    filename = f"poll_{poll_id}_results.csv"
    await message.answer_document(InputFile(io.BytesIO(data_bytes), filename=filename))

    await state.finish()
    return await return_to_main_menu(message)


def register_poll_management(dp: Dispatcher):
    dp.register_message_handler(start_delete_poll, text="🗑 Удалить опрос", state="*")
    dp.register_message_handler(choose_delete_poll, state=DeletePollStates.choosing)
    dp.register_message_handler(confirm_delete_poll, state=DeletePollStates.confirming)

    dp.register_message_handler(start_export_poll, text="📥 Экспорт результатов", state="*")
    dp.register_message_handler(choose_export_poll, state=ExportPollStates.choosing)
