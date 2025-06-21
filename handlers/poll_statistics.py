# handlers/poll_statistics.py

import io
import csv

from aiogram import types, Dispatcher
from aiogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    InputFile,
    ReplyKeyboardRemove, ReplyKeyboardMarkup
)
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import StatesGroup, State

from sqlalchemy import func
from sqlalchemy.future import select

from database import AsyncSessionLocal
from models import Poll, Question, Answer, Response, User
from .common import BACK                # у вас есть?
from .back   import return_to_main_menu  # рисует главное меню

class StatStates(StatesGroup):
    choosing_poll = State()

async def start_stats(message: types.Message, state: FSMContext):
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
    await message.answer("📊 Выберите опрос:", reply_markup=kb)

async def poll_stats_callback(query: types.CallbackQuery, state: FSMContext):
    data = query.data

    if data == "stat_back":
        await query.answer()  # ack callback
        await state.finish()  # сброс FSM
        await query.message.delete()  # удаляем старое сообщение

        # 1) Реальный ID юзера:
        user_id = query.from_user.id

        # 2) Подтягиваем роль из БД
        async with AsyncSessionLocal() as s:
            me = (await s.execute(
                select(User).where(User.tg_id == user_id)
            )).scalar_one_or_none()

        role = me.role if me else None

        # 3) Собираем главное меню «в лоб»
        kb = ReplyKeyboardMarkup(resize_keyboard=True)
        if role == "admin":
            kb.add("👥 Пользователи", "📝 Опросы") \
                .add("🏷️ Группы", "📊 Статистика")
        elif role == "teacher":
            kb.add("👥 Пользователи", "📝 Опросы") \
                .add("🏷️ Группы", "📊 Статистика") \
                .add("📋 Пройти опрос")
        else:
            kb.add("📋 Пройти опрос")

        # 4) Отправляем меню в тот же чат
        return await query.message.answer(
            "Главное меню:", reply_markup=kb
        )

    # 1) Обработка «🔙 Назад»
    if data == "stat_back":
        await query.answer()
        await state.finish()
        await query.message.delete()
        # возвращаем главное меню из .back:
        return await return_to_main_menu(query.message)

    # 2) Собираем статистику
    poll_id = int(data.split("_", 1)[1])
    async with AsyncSessionLocal() as s:
        poll = (await s.execute(
            select(Poll).where(Poll.id == poll_id)
        )).scalar_one_or_none()
        if not poll:
            return await query.answer("❌ Опрос не найден.")

        stats = []
        qs = (await s.execute(
            select(Question).where(Question.poll_id == poll_id)
        )).scalars().all()

        for q in qs:
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
                stats.append((
                    q.question_text,
                    [(ans, cnt, cnt / total * 100) for ans, cnt in rows]
                ))
            else:
                texts = (await s.execute(
                    select(Response.response_text)
                    .where(Response.question_id == q.id)
                )).scalars().all()
                stats.append((q.question_text, [(t,) for t in texts]))

    lines = [f"📊 Статистика «{poll.title}»\n"]
    for question, rows in stats:
        lines.append(f"<b>{question}</b>")
        for row in rows:
            if len(row) == 3:
                a, c, p = row
                lines.append(f"• {a}: {c} ({p:.1f}%)")
            else:
                (txt,) = row
                lines.append(f"– {txt}")
        lines.append("")
    text = "\n".join(lines)

    kb2 = InlineKeyboardMarkup().row(
        InlineKeyboardButton("⬇️ Скачать CSV", callback_data=f"export_{poll.id}"),
        InlineKeyboardButton(BACK, callback_data="stat_back")
    )

    await state.finish()
    await query.message.edit_text(text,
                                  reply_markup=kb2,
                                  disable_web_page_preview=True)
    await query.answer()

async def export_csv(query: types.CallbackQuery):
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

        qs = (await s.execute(
            select(Question).where(Question.poll_id == poll_id)
        )).scalars().all()

        for q in qs:
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
                    for uid, txt in text_rows:
                        writer.writerow([q.question_text, uid, txt, "-"])

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
        state="*"
    )
    dp.register_callback_query_handler(
        export_csv,
        lambda c: c.data.startswith("export_"),
        state="*"
    )
