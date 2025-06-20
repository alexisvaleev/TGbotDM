# handlers/poll_statistics.py

import io
import csv

from aiogram import types, Dispatcher
from aiogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    InputFile,
    ReplyKeyboardRemove
)
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import StatesGroup, State

from sqlalchemy import func
from sqlalchemy.future import select

from database import AsyncSessionLocal
from models import Poll, Question, Answer, Response
from .common import BACK
from .back import return_to_main_menu

class StatStates(StatesGroup):
    choosing_poll = State()

async def start_stats(message: types.Message, state: FSMContext):
    """
    Показываем список опросов для статистики.
    """
    await state.finish()
    async with AsyncSessionLocal() as s:
        polls = (await s.execute(select(Poll))).scalars().all()

    if not polls:
        return await message.answer(
            "🚫 Нет опросов для статистики.",
            reply_markup=ReplyKeyboardRemove()
        )

    kb = InlineKeyboardMarkup(row_width=1)
    for p in polls:
        kb.add(InlineKeyboardButton(p.title, callback_data=f"stat_{p.id}"))
    kb.add(InlineKeyboardButton(BACK, callback_data="stat_back"))

    await StatStates.choosing_poll.set()
    await message.answer("Выберите опрос:", reply_markup=kb)

async def poll_stats_callback(query: types.CallbackQuery, state: FSMContext):
    """
    Сбор статистики по опросу и вывод текста + inline-кнопки «Скачать CSV».
    Отображает все варианты ответов, даже с нулём выборов.
    """
    data = query.data
    if data == "stat_back":
        await state.finish()
        await query.message.delete_reply_markup()
        return await return_to_main_menu(query.message)

    poll_id = int(data.split("_", 1)[1])

    async with AsyncSessionLocal() as s:
        poll = (await s.execute(
            select(Poll).where(Poll.id == poll_id)
        )).scalar_one_or_none()
        if not poll:
            return await query.answer("❌ Опрос не найден.")

        stats = []
        questions = (await s.execute(
            select(Question).where(Question.poll_id == poll_id)
        )).scalars().all()

        for q in questions:
            if q.question_type != "text":
                # Берём все варианты и считаем 0, если нет ответов
                rows = (await s.execute(
                    select(
                        Answer.answer_text,
                        func.coalesce(func.count(Response.id), 0).label("cnt")
                    )
                    .outerjoin(Response, Response.answer_id == Answer.id)
                    .where(Answer.question_id == q.id)
                    .group_by(Answer.answer_text)
                )).all()
                total = sum(cnt for _, cnt in rows) or 1
                stats.append((
                    q.question_text,
                    [(ans, cnt, cnt / total * 100) for ans, cnt in rows]
                ))
            else:
                # Все текстовые ответы
                rows = (await s.execute(
                    select(Response.response_text)
                    .where(Response.question_id == q.id)
                )).scalars().all()
                stats.append((q.question_text, [(r,) for r in rows]))

    # Формирование текстового вывода
    lines = [f"📊 Статистика опроса «{poll.title}»\n"]
    for question, rows in stats:
        lines.append(f"<b>{question}</b>")
        for row in rows:
            if len(row) == 3:
                ans, cnt, pct = row
                lines.append(f"• {ans}: {cnt} ({pct:.1f}%)")
            else:
                (resp,) = row
                lines.append(f"– {resp}")
        lines.append("")  # пустая строка между вопросами
    text = "\n".join(lines)

    kb2 = InlineKeyboardMarkup().add(
        InlineKeyboardButton("⬇️ Скачать CSV", callback_data=f"export_{poll.id}")
    )

    await state.finish()
    await query.message.edit_text(text, reply_markup=kb2, disable_web_page_preview=True)
    await query.answer()

async def export_csv(query: types.CallbackQuery):
    """
    Генерирует CSV (UTF-8+BOM) со всеми вариантами и процентами.
    """
    poll_id = int(query.data.split("_", 1)[1])

    async with AsyncSessionLocal() as s:
        poll = (await s.execute(
            select(Poll).where(Poll.id == poll_id)
        )).scalar_one_or_none()
        if not poll:
            return await query.answer("❌ Опрос не найден.")

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["Вопрос", "Ответ/Ответчик", "Количество", "Процент"])

        questions = (await s.execute(
            select(Question).where(Question.poll_id == poll_id)
        )).scalars().all()

        for q in questions:
            if q.question_type != "text":
                rows = (await s.execute(
                    select(
                        Answer.answer_text,
                        func.coalesce(func.count(Response.id), 0).label("cnt")
                    )
                    .outerjoin(Response, Response.answer_id == Answer.id)
                    .where(Answer.question_id == q.id)
                    .group_by(Answer.answer_text)
                )).all()
                total = sum(cnt for _, cnt in rows) or 1
                for ans, cnt in rows:
                    pct = cnt / total * 100
                    writer.writerow([q.question_text, ans, cnt, f"{pct:.1f}%"])
            else:
                text_rows = (await s.execute(
                    select(Response.user_id, Response.response_text)
                    .where(Response.question_id == q.id)
                )).all()
                if not text_rows:
                    writer.writerow([q.question_text, "-", "-", "-"])
                else:
                    for user_id, resp in text_rows:
                        writer.writerow([q.question_text, user_id, resp, "-"])

    # Добавляем BOM для корректного открытия в Excel
    bom = '\ufeff'.encode('utf-8')
    bio = io.BytesIO(bom + output.getvalue().encode('utf-8'))
    bio.name = f"{poll.title}.csv"

    await query.message.answer_document(InputFile(bio, bio.name))
    await query.answer("📁 CSV готов!", show_alert=True)

def register_poll_statistics(dp: Dispatcher):
    dp.register_message_handler(
        start_stats,
        text="📊 Статистика",
        state=None
    )
    dp.register_callback_query_handler(
        poll_stats_callback,
        lambda c: c.data.startswith("stat_"),
        state=StatStates.choosing_poll
    )
    dp.register_callback_query_handler(
        poll_stats_callback,
        lambda c: c.data == "stat_back"
    )
    dp.register_callback_query_handler(
        export_csv,
        lambda c: c.data.startswith("export_")
    )
