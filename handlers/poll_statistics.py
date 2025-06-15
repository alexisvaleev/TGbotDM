# handlers/poll_statistics.py

from collections import Counter
from aiogram import types, Dispatcher
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from sqlalchemy.future import select

from database import AsyncSessionLocal
from handlers.common import BACK_BTN
from handlers.back import return_to_main_menu
from handlers.start import _send_main_menu
from models import User, Poll, Question, Answer, UserAnswer

class StatsStates(StatesGroup):
    choosing_poll = State()


async def start_stats(message: types.Message, state: FSMContext):
    """Запускает выбор опроса для просмотра статистики."""
    await state.finish()
    tg = message.from_user.id

    # Проверяем, что это админ
    async with AsyncSessionLocal() as s:
        user = (await s.execute(
            select(User).where(User.tg_id == tg)
        )).scalar_one_or_none()
    if not user or user.role != "admin":
        return await message.answer("⛔ Только админ может смотреть статистику.")

    # Загружаем все опросы
    async with AsyncSessionLocal() as s:
        polls = (await s.execute(select(Poll))).scalars().all()
    if not polls:
        return await message.answer("Нет опросов для статистики.", reply_markup=BACK_BTN)

    # Строим клавиатуру с опросами
    kb = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    for idx, p in enumerate(polls, start=1):
        kb.add(KeyboardButton(f"{idx}. {p.title}"))
    kb.add(BACK_BTN)

    # Сохраняем ID-список и переводим FSM в выбор
    await state.update_data(poll_ids=[p.id for p in polls])
    await StatsStates.choosing_poll.set()
    await message.answer("Выберите опрос для просмотра статистики:", reply_markup=kb)


async def choose_poll_stats(message: types.Message, state: FSMContext):
    """Показывает процентную статистику и возвращает в главное меню."""
    txt = message.text.strip()
    if txt == BACK_BTN:
        await state.finish()
        return await return_to_main_menu(message)

    data = await state.get_data()
    poll_ids = data.get("poll_ids", [])
    parts = txt.split(".", 1)
    if not parts[0].isdigit():
        return await message.answer("Пожалуйста, нажмите на кнопку с номером опроса.")
    idx = int(parts[0]) - 1
    if idx < 0 or idx >= len(poll_ids):
        return await message.answer("Неверный номер опроса.")

    poll_id = poll_ids[idx]

    # Формируем текст статистики
    lines = [f"📊 Статистика опроса: #{poll_id}\n"]
    async with AsyncSessionLocal() as s:
        questions = (await s.execute(
            select(Question).where(Question.poll_id == poll_id)
        )).scalars().all()

        for q in questions:
            lines.append(f"🔹 {q.question_text}")
            uas = (await s.execute(
                select(UserAnswer).where(UserAnswer.question_id == q.id)
            )).scalars().all()
            total = len(uas)
            opts = (await s.execute(
                select(Answer).where(Answer.question_id == q.id)
            )).scalars().all()

            if opts:
                cnt = Counter(ua.answer_text for ua in uas)
                for o in opts:
                    c = cnt.get(o.answer_text, 0)
                    pct = (c / total * 100) if total else 0
                    lines.append(f"    • {o.answer_text}: {c}/{total} ({pct:.1f}%)")
            else:
                lines.append(f"    • Текстовых ответов: {total}")
            lines.append("")

    # Сброс FSM и возврат в меню
    await state.finish()
    # Отправляем статистику
    await message.answer("\n".join(lines), reply_markup=ReplyKeyboardMarkup(resize_keyboard=True).add(BACK_BTN))
    # И сразу же главное меню
    return await _send_main_menu(message, user.role if (user := await _get_user(message.from_user.id)) else "unknown")


async def _get_user(tg_id: int):
    """Вспомогательный: подтягиваем юзера из БД."""
    async with AsyncSessionLocal() as s:
        return (await s.execute(select(User).where(User.tg_id == tg_id))).scalar_one_or_none()


def register_poll_statistics(dp: Dispatcher):
    dp.register_message_handler(start_stats, text="📊 Статистика", state="*")
    dp.register_message_handler(choose_poll_stats, state=StatsStates.choosing_poll)
