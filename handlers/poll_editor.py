# handlers/poll_editor.py

import io
import csv
from handlers.common import BACK_BTN
from handlers.back import return_to_main_menu
from aiogram import types, Dispatcher
from aiogram.types import (
    ReplyKeyboardRemove,
    ReplyKeyboardMarkup,
    KeyboardButton
)
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import StatesGroup, State
from sqlalchemy import select, delete

from database import AsyncSessionLocal
from models import User, Poll, Question, Answer, Group

class PollEditorStates(StatesGroup):
    choosing_poll         = State()  # выбор опроса
    choosing_mode         = State()  # параметры или вопросы
    # параметры опроса
    choosing_field        = State()
    editing_title         = State()
    editing_target        = State()
    editing_group         = State()
    # редактирование вопросов
    choosing_question     = State()
    action_menu           = State()
    editing_q_text        = State()
    adding_option         = State()
    choosing_opt_to_del   = State()
    confirming_opt_delete = State()

async def start_poll_editor(message: types.Message, state: FSMContext):
    """Шаг 1. Админ нажал «✏️ Редактировать опрос»."""
    tg_id = message.from_user.id
    # Проверяем роль
    async with AsyncSessionLocal() as s:
        user = (await s.execute(
            select(User).where(User.tg_id == tg_id)
        )).scalar()
    if not user or user.role not in ("admin", "teacher"):
        return await message.answer("⛔ Только админы могут редактировать опросы.")

    # Получаем список опросов
    async with AsyncSessionLocal() as s:
        polls = (await s.execute(select(Poll))).scalars().all()
    if not polls:
        return await message.answer("Нет опросов для редактирования.")

    # Сохраняем id опросов в FSM и показываем меню
    await state.update_data(poll_ids=[p.id for p in polls])
    text = "✏️ Выберите опрос для редактирования:\n" + "\n".join(
        f"{i+1}. {p.title}" for i, p in enumerate(polls)
    )
    await state.set_state(PollEditorStates.choosing_poll)
    await message.answer(text, reply_markup=ReplyKeyboardRemove())

async def choose_poll(message: types.Message, state: FSMContext):
    """Шаг 2. Админ вводит номер опроса."""
    data = await state.get_data()
    poll_ids = data.get("poll_ids", [])
    if not message.text.isdigit():
        return await message.answer("Введите номер опроса цифрой.")
    idx = int(message.text) - 1
    if idx < 0 or idx >= len(poll_ids):
        return await message.answer("Неверный номер.")
    poll_id = poll_ids[idx]
    await state.update_data(edit_poll_id=poll_id)

    # Меню: параметры или вопросы
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(KeyboardButton("🔤 Параметры опроса"))
    kb.add(KeyboardButton("📝 Вопросы"))
    kb.add(KeyboardButton("❌ Готово"))
    kb.add(BACK_BTN)
    kb.add(BACK_BTN)
    await state.set_state(PollEditorStates.choosing_mode)
    await message.answer("Что будем править?", reply_markup=kb)

async def choose_mode(message: types.Message, state: FSMContext):
    """Шаг 3. Выбор режима редактирования."""
    text = message.text.strip()
    if text == "🔤 Параметры опроса":
        kb = ReplyKeyboardMarkup(resize_keyboard=True)
        kb.add(KeyboardButton("🔤 Название"))
        kb.add(KeyboardButton("👥 Аудитория"))
        kb.add(KeyboardButton("🏷 Группа"))
        kb.add(KeyboardButton("❌ Отмена"))
        kb.add(BACK_BTN)
        await state.set_state(PollEditorStates.choosing_field)
        return await message.answer("Что правим в параметрах?", reply_markup=kb)

    if text == "📝 Вопросы":
        data = await state.get_data()
        return await _ask_choose_question(message, state, data["edit_poll_id"])

    # ❌ Готово
    await state.finish()
    return await return_to_main_menu(message)

# ----- Параметры опроса -----

async def process_field_choice(message: types.Message, state: FSMContext):
    """Шаг 4. Выбираем что правим в параметрах."""
    text = message.text.strip()
    if text == "🔤 Название":
        await state.set_state(PollEditorStates.editing_title)
        return await message.answer("Введите новый заголовок:", reply_markup=ReplyKeyboardRemove())

    if text == "👥 Аудитория":
        kb = ReplyKeyboardMarkup(resize_keyboard=True)
        kb.add(KeyboardButton("teacher"), KeyboardButton("student"), KeyboardButton("все"))
        kb.add(BACK_BTN)
        await state.set_state(PollEditorStates.editing_target)
        return await message.answer("Выберите новую аудиторию:", reply_markup=kb)

    if text == "🏷 Группа":
        async with AsyncSessionLocal() as s:
            groups = (await s.execute(select(Group))).scalars().all()
        if not groups:
            return await message.answer("Сначала создайте группы.")
        kb = ReplyKeyboardMarkup(resize_keyboard=True)
        for g in groups:
            kb.add(KeyboardButton(g.name))
        kb.add(KeyboardButton("❌ Без группы"))
        kb.add(BACK_BTN)
        await state.set_state(PollEditorStates.editing_group)
        return await message.answer("Выберите группу:", reply_markup=kb)

    # ❌ Отмена
    await state.set_state(PollEditorStates.choosing_mode)
    return await message.answer("Отмена. Что дальше?", reply_markup=ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton("🔤 Параметры опроса")],
            [KeyboardButton("📝 Вопросы")],
            [KeyboardButton("❌ Готово")]
        ],
        resize_keyboard=True
    ))

async def process_edit_title(message: types.Message, state: FSMContext):
    """Шаг 5а. Сохраняем новый заголовок."""
    new_title = message.text.strip()
    data = await state.get_data()
    poll_id = data["edit_poll_id"]
    async with AsyncSessionLocal() as s:
        await s.execute(
            Poll.__table__
            .update().where(Poll.id == poll_id)
            .values(title=new_title)
        )
        await s.commit()
    await message.answer("✅ Заголовок обновлён.", reply_markup=ReplyKeyboardRemove())
    await _return_to_mode_menu(message, state)

async def process_edit_target(message: types.Message, state: FSMContext):
    """Шаг 5б. Сохраняем новую аудиторию."""
    new_target = message.text.strip()
    if new_target not in ("teacher", "student", "все"):
        return await message.answer("Выберите один из предложенных вариантов.")
    data = await state.get_data()
    poll_id = data["edit_poll_id"]
    async with AsyncSessionLocal() as s:
        await s.execute(
            Poll.__table__
            .update().where(Poll.id == poll_id)
            .values(target_role=new_target)
        )
        await s.commit()
    await message.answer("✅ Аудитория обновлена.", reply_markup=ReplyKeyboardRemove())
    await _return_to_mode_menu(message, state)

async def process_edit_group(message: types.Message, state: FSMContext):
    """Шаг 5в. Сохраняем новую группу."""
    choice = message.text.strip()
    data = await state.get_data()
    poll_id = data["edit_poll_id"]
    async with AsyncSessionLocal() as s:
        if choice == "❌ Без группы":
            grp_id = None
        else:
            grp = (await s.execute(select(Group).where(Group.name == choice))).scalar()
            if not grp:
                return await message.answer("Нажмите кнопку с названием группы.")
            grp_id = grp.id
        await s.execute(
            Poll.__table__
            .update().where(Poll.id == poll_id)
            .values(group_id=grp_id)
        )
        await s.commit()
    await message.answer("✅ Группа обновлена.", reply_markup=ReplyKeyboardRemove())
    await _return_to_mode_menu(message, state)

# ----- Редактирование вопросов -----

async def _ask_choose_question(message: types.Message, state: FSMContext, poll_id: int):
    """Список вопросов для выбранного опроса."""
    async with AsyncSessionLocal() as s:
        qs = (await s.execute(select(Question).where(Question.poll_id == poll_id))).scalars().all()
    if not qs:
        await message.answer("У опроса нет вопросов.", reply_markup=ReplyKeyboardRemove())
        return await _return_to_mode_menu(message, state)

    await state.update_data(question_ids=[q.id for q in qs])
    text = "📝 Выберите вопрос:\n" + "\n".join(
        f"{i+1}. {q.question_text}" for i, q in enumerate(qs)
    )
    await state.set_state(PollEditorStates.choosing_question)
    await message.answer(text, reply_markup=ReplyKeyboardRemove())

async def choose_question(message: types.Message, state: FSMContext):
    """Шаг 6. Админ выбирает вопрос."""
    data = await state.get_data()
    q_ids = data.get("question_ids", [])
    if not message.text.isdigit():
        return await message.answer("Введите номер вопроса цифрой.")
    idx = int(message.text) - 1
    if idx < 0 or idx >= len(q_ids):
        return await message.answer("Неверный номер.")
    q_id = q_ids[idx]
    await state.update_data(edit_q_id=q_id)

    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(KeyboardButton("🔤 Изменить текст"))
    kb.add(KeyboardButton("➕ Добавить вариант"))
    kb.add(KeyboardButton("✂️ Удалить вариант"))
    kb.add(KeyboardButton("❌ Готово"))
    kb.add(BACK_BTN)
    await state.set_state(PollEditorStates.action_menu)
    await message.answer("Выберите действие с вопросом:", reply_markup=kb)

async def action_menu_handler(message: types.Message, state: FSMContext):
    """Шаг 7. Меню действий над вопросом."""
    text = message.text.strip()
    if text == "🔤 Изменить текст":
        await state.set_state(PollEditorStates.editing_q_text)
        return await message.answer("Введите новый текст вопроса:", reply_markup=ReplyKeyboardRemove())

    if text == "➕ Добавить вариант":
        await state.set_state(PollEditorStates.adding_option)
        return await message.answer("Отправьте текст нового варианта:", reply_markup=ReplyKeyboardRemove())

    if text == "✂️ Удалить вариант":
        data = await state.get_data()
        q_id = data["edit_q_id"]
        async with AsyncSessionLocal() as s:
            opts = (await s.execute(select(Answer).where(Answer.question_id == q_id))).scalars().all()
        if not opts:
            return await message.answer("У этого вопроса нет вариантов.")
        kb = ReplyKeyboardMarkup(resize_keyboard=True)
        for i, opt in enumerate(opts):
            kb.add(KeyboardButton(f"{i+1}. {opt.answer_text}"))
        await state.set_state(PollEditorStates.choosing_opt_to_del)
        return await message.answer("Выберите вариант для удаления:", reply_markup=kb)

    # ❌ Готово — возвращаемся к режиму редактирования опроса
    await state.set_state(PollEditorStates.choosing_mode)
    return await choose_mode(message, state)

async def process_editing_q_text(message: types.Message, state: FSMContext):
    """Шаг 8а. Сохраняем новый текст вопроса."""
    new_text = message.text.strip()
    data = await state.get_data()
    q_id = data["edit_q_id"]
    async with AsyncSessionLocal() as s:
        await s.execute(
            Question.__table__
            .update().where(Question.id == q_id)
            .values(question_text=new_text)
        )
        await s.commit()
    await message.answer("✅ Текст вопроса обновлён.", reply_markup=ReplyKeyboardRemove())
    await _return_to_actions(message, state)

async def process_adding_option(message: types.Message, state: FSMContext):
    """Шаг 8б. Добавляем новый вариант ответа."""
    opt_text = message.text.strip()
    data = await state.get_data()
    q_id = data["edit_q_id"]
    async with AsyncSessionLocal() as s:
        s.add(Answer(question_id=q_id, answer_text=opt_text))
        await s.commit()
    await message.answer(f"✅ Вариант '{opt_text}' добавлен.", reply_markup=ReplyKeyboardRemove())
    await _return_to_actions(message, state)

async def choose_option_to_delete(message: types.Message, state: FSMContext):
    """Шаг 8в. Выбираем вариант для удаления."""
    text = message.text.strip()
    if ". " not in text:
        return await message.answer("Нажмите кнопку с вариантом.")
    idx = int(text.split(".")[0]) - 1
    data = await state.get_data()
    q_id = data["edit_q_id"]
    async with AsyncSessionLocal() as s:
        opts = (await s.execute(select(Answer).where(Answer.question_id == q_id))).scalars().all()
    if idx < 0 or idx >= len(opts):
        return await message.answer("Неверный выбор.")
    answer = opts[idx]
    await state.update_data(del_opt_id=answer.id)

    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(KeyboardButton("✅ Да"), KeyboardButton("❌ Нет"))
    await state.set_state(PollEditorStates.confirming_opt_delete)
    await message.answer(f"Удалить вариант '{answer.answer_text}'?", reply_markup=kb)

async def confirm_option_delete(message: types.Message, state: FSMContext):
    """Шаг 8г. Подтверждаем удаление варианта."""
    ans = message.text.strip()
    data = await state.get_data()
    opt_id = data["del_opt_id"]
    if ans == "✅ Да":
        async with AsyncSessionLocal() as s:
            await s.execute(delete(Answer).where(Answer.id == opt_id))
            await s.commit()
        await message.answer("✅ Вариант удалён.", reply_markup=ReplyKeyboardRemove())
    else:
        await message.answer("❌ Удаление отменено.", reply_markup=ReplyKeyboardRemove())
    await _return_to_actions(message, state)

# ====== Вспомогательные ======

async def _return_to_mode_menu(message: types.Message, state: FSMContext):
    """После правки параметров возвращаем выбор режима."""
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(KeyboardButton("🔤 Параметры опроса"))
    kb.add(KeyboardButton("📝 Вопросы"))
    kb.add(KeyboardButton("❌ Готово"))
    await state.set_state(PollEditorStates.choosing_mode)
    await message.answer("Что правим дальше?", reply_markup=kb)

async def _return_to_actions(message: types.Message, state: FSMContext):
    """После правки вопроса возвращаем меню действий над вопросом."""
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(KeyboardButton("🔤 Изменить текст"))
    kb.add(KeyboardButton("➕ Добавить вариант"))
    kb.add(KeyboardButton("✂️ Удалить вариант"))
    kb.add(KeyboardButton("❌ Готово"))
    await state.set_state(PollEditorStates.action_menu)
    await message.answer("Выберите действие:", reply_markup=kb)

async def _return_to_admin_menu(message: types.Message):
    await return_to_main_menu(message)

def register_poll_editor(dp: Dispatcher):
    dp.register_message_handler(start_poll_editor, text="✏️ Редактировать опрос", state="*")
    dp.register_message_handler(choose_poll, state=PollEditorStates.choosing_poll)
    dp.register_message_handler(choose_mode, state=PollEditorStates.choosing_mode)

    # Параметры опроса
    dp.register_message_handler(process_field_choice, state=PollEditorStates.choosing_field)
    dp.register_message_handler(process_edit_title, state=PollEditorStates.editing_title)
    dp.register_message_handler(process_edit_target, state=PollEditorStates.editing_target)
    dp.register_message_handler(process_edit_group, state=PollEditorStates.editing_group)

    # Редактирование вопросов
    dp.register_message_handler(choose_question, state=PollEditorStates.choosing_question)
    dp.register_message_handler(action_menu_handler, state=PollEditorStates.action_menu)
    dp.register_message_handler(process_editing_q_text, state=PollEditorStates.editing_q_text)
    dp.register_message_handler(process_adding_option, state=PollEditorStates.adding_option)
    dp.register_message_handler(choose_option_to_delete, state=PollEditorStates.choosing_opt_to_del)
    dp.register_message_handler(confirm_option_delete, state=PollEditorStates.confirming_opt_delete)
