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
from sqlalchemy import delete, select, update

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

class DeletePollStates(StatesGroup):
    choosing = State()
    confirming = State()


class ExportPollStates(StatesGroup):
    choosing = State()


async def start_delete_poll(message: types.Message, state: FSMContext):
    """Шаг 1. Админ выбирает опрос для удаления."""
    tg_id = message.from_user.id
    # Проверяем, что это админ
    async with AsyncSessionLocal() as session:
        user = (await session.execute(
            select(User).where(User.tg_id == tg_id)
        )).scalar()
    if not user or user.role not in ("admin", "teacher"):
        return await message.answer("⛔ Только админы могут удалять опросы.")

    # Получаем все опросы
    async with AsyncSessionLocal() as session:
        polls = (await session.execute(select(Poll))).scalars().all()
    if not polls:
        return await message.answer("Нет опросов для удаления.")

    # Сохраняем список id в FSM и выводим меню
    await state.update_data(poll_ids=[p.id for p in polls])
    text = "🗑 Выберите опрос для удаления:\n" + "\n".join(
        f"{i+1}. {p.title}" for i, p in enumerate(polls)
    )
    await state.set_state(DeletePollStates.choosing.state)
    await message.answer(text, reply_markup=ReplyKeyboardRemove())


async def choose_delete_poll(message: types.Message, state: FSMContext):
    """Шаг 2. Админ вводит номер опроса."""
    data = await state.get_data()
    poll_ids = data.get("poll_ids", [])
    if not message.text.isdigit():
        return await message.answer("Введите, пожалуйста, номер опроса.")
    idx = int(message.text) - 1
    if idx < 0 or idx >= len(poll_ids):
        return await message.answer("Неверный номер.")
    chosen_id = poll_ids[idx]

    await state.update_data(chosen_id=chosen_id)
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(KeyboardButton("✅ Да"), KeyboardButton("❌ Нет"))
    await state.set_state(DeletePollStates.confirming.state)
    await message.answer("⚠️ Подтвердите удаление опроса:", reply_markup=kb)


async def confirm_delete_poll(message: types.Message, state: FSMContext):
    """Шаг 3. Админ подтверждает или отменяет удаление."""
    answer = message.text.strip()
    data = await state.get_data()
    poll_id = data.get("chosen_id")

    if answer != "✅ Да":
        await message.answer("❌ Удаление отменено.", reply_markup=ReplyKeyboardRemove())
        await _return_to_admin_menu(message)
        await state.finish()
        return

    async with AsyncSessionLocal() as session:
        try:
            # 0) Сначала обнуляем last_question_id у всех прогрессов этого опроса
            await session.execute(
                update(UserPollProgress)
                .where(UserPollProgress.poll_id == poll_id)
                .values(last_question_id=None)
            )

            # 1) Удаляем прогресс прохождения
            await session.execute(
                delete(UserPollProgress).where(UserPollProgress.poll_id == poll_id)
            )
            # 2) Собираем question_ids
            q_res = await session.execute(
                select(Question.id).where(Question.poll_id == poll_id)
            )
            question_ids = [q_id for (q_id,) in q_res.all()]

            if question_ids:
                # 3) Удаляем ответы пользователей на эти вопросы
                await session.execute(
                    delete(UserAnswer).where(UserAnswer.question_id.in_(question_ids))
                )
                # 4) Удаляем варианты Answer
                await session.execute(
                    delete(Answer).where(Answer.question_id.in_(question_ids))
                )
                # 5) Удаляем сами вопросы
                await session.execute(
                    delete(Question).where(Question.id.in_(question_ids))
                )

            # 6) Наконец удаляем сам Poll
            await session.execute(
                delete(Poll).where(Poll.id == poll_id)
            )

            await session.commit()
            await message.answer("✅ Опрос и все связанные данные удалены.")
        except Exception as e:
            await session.rollback()
            print("Ошибка при каскадном удалении:", e)
            await message.answer("⚠️ Ошибка при удалении опроса.")

    await _return_to_admin_menu(message)
    await state.finish()


async def start_export_poll(message: types.Message, state: FSMContext):
    """Шаг 1. Админ выбирает опрос для экспорта в CSV."""
    tg_id = message.from_user.id
    async with AsyncSessionLocal() as session:
        user = (await session.execute(
            select(User).where(User.tg_id == tg_id)
        )).scalar()
    if not user or user.role != "admin":
        return await message.answer("⛔ Только админы могут экспортировать результаты.")

    async with AsyncSessionLocal() as session:
        polls = (await session.execute(select(Poll))).scalars().all()
    if not polls:
        return await message.answer("Нет опросов для экспорта.")

    await state.update_data(poll_ids=[p.id for p in polls])
    text = "📥 Выберите опрос для экспорта:\n" + "\n".join(
        f"{i+1}. {p.title}" for i, p in enumerate(polls)
    )
    await state.set_state(ExportPollStates.choosing.state)
    await message.answer(text, reply_markup=ReplyKeyboardRemove())


async def choose_export_poll(message: types.Message, state: FSMContext):
    """Шаг 2. Собираем результаты и отдаем CSV."""
    data = await state.get_data()
    poll_ids = data.get("poll_ids", [])
    if not message.text.isdigit():
        return await message.answer("Введите номер опроса.")
    idx = int(message.text) - 1
    if idx < 0 or idx >= len(poll_ids):
        return await message.answer("Неверный номер.")
    poll_id = poll_ids[idx]

    # Формируем CSV
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["question_id", "question_text", "user_tg_id", "answer_text"])

    async with AsyncSessionLocal() as session:
        # Получаем все вопросы опроса
        questions = (await session.execute(
            select(Question).where(Question.poll_id == poll_id)
        )).scalars().all()

        # Для каждого вопроса собираем ответы
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

    # Отправляем файл
    output.seek(0)
    file_bytes = output.getvalue().encode("utf-8")
    filename = f"poll_{poll_id}_results.csv"
    await message.answer_document(
        InputFile(io.BytesIO(file_bytes), filename=filename)
    )

    await _return_to_admin_menu(message)
    await state.finish()


async def _return_to_admin_menu(message: types.Message):
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(KeyboardButton("📊 Статистика"))
    kb.add(KeyboardButton("➕ Создать опрос"), KeyboardButton("🗑 Удалить опрос"))
    kb.add(KeyboardButton("📥 Экспорт результатов"))
    kb.add(KeyboardButton("👥 Управление пользователями"))
    await message.answer("Выберите действие:", reply_markup=kb)


def register_poll_management(dp: Dispatcher):
    dp.register_message_handler(
        start_delete_poll, text="🗑 Удалить опрос", state="*"
    )
    dp.register_message_handler(
        choose_delete_poll, state=DeletePollStates.choosing
    )
    dp.register_message_handler(
        confirm_delete_poll, state=DeletePollStates.confirming
    )

    dp.register_message_handler(
        start_export_poll, text="📥 Экспорт результатов", state="*"
    )
    dp.register_message_handler(
        choose_export_poll, state=ExportPollStates.choosing
    )
