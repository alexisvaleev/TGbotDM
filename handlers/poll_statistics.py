# handlers/poll_statistics.py

from collections import Counter
from aiogram import types, Dispatcher
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from sqlalchemy.future import select

from database import AsyncSessionLocal
from models import User, Poll, Question, Answer, UserAnswer
from handlers.common import BACK, BACK_BTN
from handlers.back import return_to_main_menu

class StatsStates(StatesGroup):
    choosing_poll = State()

async def start_stats(message: types.Message, state: FSMContext):
    """Шаг 1. Админ запускает статистику."""
    tg = message.from_user.id
    async with AsyncSessionLocal() as s:
        user = (await s.execute(
            select(User).where(User.tg_id == tg)
        )).scalar_one_or_none()

    if not user or user.role != "admin":
        return await message.answer("⛔ Только админ может смотреть статистику.")

    # выбираем все опросы
    async with AsyncSessionLocal() as s:
        polls = (await s.execute(select(Poll))).scalars().all()

    if not polls:
        return await message.answer("Нет опросов для статистики.", reply_markup=BACK_BTN)

    # сохраняем список и предлагаем выбрать
    await state.update_data(poll_ids=[p.id for p in polls])
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    for i, p in enumerate(polls, 1):
        kb.add(types.KeyboardButton(f"{i}. {p.title}"))
    kb.add(BACK_BTN)

    await StatsStates.choosing_poll.set()
    await message.answer("Выберите опрос для просмотра статистики:", reply_markup=kb)

async def choose_poll_stats(message: types.Message, state: FSMContext):
    """Шаг 2. Собираем и показываем процентную статистику."""
    text = message.text.strip()
    if text == BACK:
        await state.finish()
        return await return_to_main_menu(message)

    data = await state.get_data()
    ids = data.get("poll_ids", [])
    if ". " not in text or not text.split(".")[0].isdigit():
        return await message.answer("Нажмите кнопку с номером опроса.")
    idx = int(text.split(".")[0]) - 1
    if idx < 0 or idx >= len(ids):
        return await message.answer("Неверный номер.")

    poll_id = ids[idx]

    # грузим вопросы и ответы
    async with AsyncSessionLocal() as s:
        qs = (await s.execute(
            select(Question).where(Question.poll_id == poll_id)
        )).scalars().all()

    if not qs:
        await state.finish()
        return await message.answer("В этом опросе нет вопросов.", reply_markup=BACK_BTN)

    out_lines = [f"📊 Статистика для опроса #{poll_id}:\n"]
    async with AsyncSessionLocal() as s:
        for q in qs:
            out_lines.append(f"🔹 {q.question_text}")
            # собираем все ответы пользователей
            uas = (await s.execute(
                select(UserAnswer).where(UserAnswer.question_id == q.id)
            )).scalars().all()
            total = len(uas)
            if q.question_type == "single_choice":
                # получаем возможные варианты
                opts = (await s.execute(
                    select(Answer).where(Answer.question_id == q.id)
                )).scalars().all()
                cnt = Counter([ua.answer_text for ua in uas])

                for opt in opts:
                    c = cnt.get(opt.answer_text, 0)
                    pct = (c / total * 100) if total else 0
                    out_lines.append(f"    • {opt.answer_text}: {c}/{total} ({pct:.1f}%)")
            else:
                # текстовый вопрос: просто число ответов
                out_lines.append(f"    • Всего ответов: {total}")
            out_lines.append("")  # пустая строка между вопросами

    await state.finish()
    await message.answer("\n".join(out_lines), reply_markup=BACK_BTN)

def register_poll_statistics(dp: Dispatcher):
    dp.register_message_handler(start_stats,
                                text="📊 Статистика",
                                state="*")
    dp.register_message_handler(choose_poll_stats,
                                state=StatsStates.choosing_poll)
