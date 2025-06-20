# handlers/poll_statistics.py

from collections import Counter
from aiogram import types, Dispatcher
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from sqlalchemy.future import select

from database import AsyncSessionLocal
from models import User, Poll, Question, Answer, UserAnswer
from handlers.common import BACK, BACK_BTN
from handlers.back import return_to_main_menu


class StatsStates(StatesGroup):
    choosing_poll = State()


async def start_stats(message: types.Message, state: FSMContext):
    """
    Запускается по кнопке 📊 Статистика.
    Только admin и teacher могут просматривать.
    """
    await state.finish()
    tg = message.from_user.id

    # проверяем роль
    async with AsyncSessionLocal() as s:
        me = (await s.execute(
            select(User).where(User.tg_id == tg)
        )).scalar_one_or_none()

    if not me or me.role not in ("admin", "teacher"):
        return await message.answer(
            "⛔ Только админ или преподаватель может смотреть статистику."
        )

    # загружаем все опросы
    async with AsyncSessionLocal() as s:
        polls = (await s.execute(select(Poll))).scalars().all()

    if not polls:
        return await message.answer("🚫 Нет опросов для статистики.", reply_markup=BACK_BTN)

    # строим клавиатуру выбора
    kb = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    for idx, p in enumerate(polls, start=1):
        kb.add(KeyboardButton(f"{idx}. {p.title}"))
    kb.add(BACK_BTN)

    # сохраняем список id и переходим в state
    await state.update_data(poll_ids=[p.id for p in polls])
    await StatsStates.choosing_poll.set()
    await message.answer("Выберите опрос для просмотра статистики:", reply_markup=kb)


async def choose_poll_stats(message: types.Message, state: FSMContext):
    """
    После выбора опроса строим процентную статистику по каждому вопросу
    и возвращаемся в главное меню.
    """
    text = message.text.strip()
    if text == BACK:
        await state.finish()
        return await return_to_main_menu(message)

    data = await state.get_data()
    poll_ids = data.get("poll_ids", [])
    parts = text.split(".", 1)
    if not parts[0].isdigit():
        return await message.answer("Пожалуйста, нажмите кнопку с номером опроса.")
    idx = int(parts[0]) - 1
    if idx < 0 or idx >= len(poll_ids):
        return await message.answer("Неверный номер опроса.")

    poll_id = poll_ids[idx]

    # собираем статистику
    lines = [f"📊 Статистика опроса: {poll_id}\n"]
    async with AsyncSessionLocal() as s:
        questions = (await s.execute(
            select(Question).where(Question.poll_id == poll_id)
        )).scalars().all()

        for q in questions:
            lines.append(f"🔹 {q.question_text}")
            answers = (await s.execute(
                select(UserAnswer).where(UserAnswer.question_id == q.id)
            )).scalars().all()
            total = len(answers)

            # варианты
            opts = (await s.execute(
                select(Answer).where(Answer.question_id == q.id)
            )).scalars().all()

            if opts:
                cnt = Counter(a.answer_text for a in answers)
                for o in opts:
                    c = cnt.get(o.answer_text, 0)
                    pct = (c / total * 100) if total else 0
                    lines.append(f"    • {o.answer_text}: {c}/{total} ({pct:.1f}%)")
            else:
                lines.append(f"    • Текстовых ответов: {total}")
            lines.append("")  # пустая строка

    # сбрасываем FSM и возвращаем в меню
    await state.finish()
    await message.answer("\n".join(lines), reply_markup=ReplyKeyboardRemove())
    return await return_to_main_menu(message)


def register_poll_statistics(dp: Dispatcher):
    dp.register_message_handler(start_stats, text="📊 Статистика", state="*")
    dp.register_message_handler(choose_poll_stats, state=StatsStates.choosing_poll)
