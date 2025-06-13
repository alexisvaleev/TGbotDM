# handlers/poll_edit.py
from aiogram import types, Dispatcher
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import StatesGroup, State
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from sqlalchemy.future import select
from database import AsyncSessionLocal
from models import Poll, Group, User

class EditPollStates(StatesGroup):
    choosing_poll   = State()  # выбираем опрос
    choosing_field  = State()  # выбираем, что правим
    editing_title   = State()  # ввод нового заголовка
    editing_target  = State()  # выбор новой целевой аудитории
    editing_group   = State()  # выбор новой группы


async def start_edit_poll(message: types.Message, state: FSMContext):
    """Шаг 1. Админ нажал «✏️ Редактировать опрос»."""
    tg_id = message.from_user.id
    # Проверяем роль
    async with AsyncSessionLocal() as session:
        user = (await session.execute(
            select(User).where(User.tg_id == tg_id)
        )).scalar()
    if not user or user.role != "admin":
        return await message.answer("⛔ Только админы могут редактировать опросы.")
    # Берём все опросы
    async with AsyncSessionLocal() as session:
        polls = (await session.execute(select(Poll))).scalars().all()
    if not polls:
        return await message.answer("Нет опросов для редактирования.")
    # Сохраняем список ID и показываем меню
    await state.update_data(poll_ids=[p.id for p in polls])
    text = "✏️ Выберите опрос для редактирования:\n" + "\n".join(
        f"{i+1}. {p.title}" for i, p in enumerate(polls)
    )
    await state.set_state(EditPollStates.choosing_poll)
    await message.answer(text, reply_markup=ReplyKeyboardRemove())

async def choose_edit_poll(message: types.Message, state: FSMContext):
    """Шаг 2. Админ вводит номер опроса из списка."""
    data = await state.get_data()
    poll_ids = data.get("poll_ids", [])
    if not message.text.isdigit():
        return await message.answer("Введите номер опроса цифрой.")
    idx = int(message.text) - 1
    if idx < 0 or idx >= len(poll_ids):
        return await message.answer("Неверный номер.")
    poll_id = poll_ids[idx]
    await state.update_data(edit_poll_id=poll_id)
    # Предлагаем, что будем править
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(KeyboardButton("🔤 Название"))
    kb.add(KeyboardButton("👥 Целевая аудитория"))
    kb.add(KeyboardButton("🏷 Группа"))
    kb.add(KeyboardButton("❌ Отмена"))
    await state.set_state(EditPollStates.choosing_field)
    await message.answer("Что хотите изменить?", reply_markup=kb)

async def choose_edit_field(message: types.Message, state: FSMContext):
    """Шаг 3. Админ выбирает поле."""
    text = message.text.strip()
    if text == "🔤 Название":
        await state.set_state(EditPollStates.editing_title)
        return await message.answer("Введите новый заголовок опроса:", reply_markup=ReplyKeyboardRemove())
    if text == "👥 Целевая аудитория":
        kb = ReplyKeyboardMarkup(resize_keyboard=True)
        kb.add(KeyboardButton("teacher"), KeyboardButton("student"), KeyboardButton("все"))
        await state.set_state(EditPollStates.editing_target)
        return await message.answer("Выберите новую аудиторию:", reply_markup=kb)
    if text == "🏷 Группа":
        # Список групп
        async with AsyncSessionLocal() as session:
            groups = (await session.execute(select(Group))).scalars().all()
        if not groups:
            return await message.answer("В системе нет групп.")
        kb = ReplyKeyboardMarkup(resize_keyboard=True)
        for g in groups:
            kb.add(KeyboardButton(g.name))
        kb.add(KeyboardButton("❌ Без группы"))
        await state.set_state(EditPollStates.editing_group)
        return await message.answer("Выберите группу для опроса:", reply_markup=kb)
    # Отмена
    await state.finish()
    await return_to_admin_menu(message)
    await message.answer("❌ Редактирование отменено.", reply_markup=ReplyKeyboardRemove())

async def process_edit_title(message: types.Message, state: FSMContext):
    """Шаг 4а. Обновляем название."""
    new_title = message.text.strip()
    data = await state.get_data()
    poll_id = data["edit_poll_id"]
    async with AsyncSessionLocal() as session:
        await session.execute(
            Poll.__table__
            .update().where(Poll.id == poll_id)
            .values(title=new_title)
        )
        await session.commit()
    await message.answer("✅ Название опроса обновлено.", reply_markup=ReplyKeyboardRemove())
    await state.finish()
    await return_to_admin_menu(message)


async def process_edit_target(message: types.Message, state: FSMContext):
    """Шаг 4б. Обновляем целевую аудиторию."""
    new_target = message.text.strip()
    if new_target not in ("teacher", "student", "все"):
        return await message.answer("Выберите один из предложенных вариантов.")
    data = await state.get_data()
    poll_id = data["edit_poll_id"]
    async with AsyncSessionLocal() as session:
        await session.execute(
            Poll.__table__
            .update().where(Poll.id == poll_id)
            .values(target_role=new_target)
        )
        await session.commit()
    await message.answer("✅ Целевая аудитория обновлена.", reply_markup=ReplyKeyboardRemove())
    await state.finish()
    await return_to_admin_menu(message)


async def process_edit_group(message: types.Message, state: FSMContext):
    """Шаг 4в. Обновляем группу."""
    choice = message.text.strip()
    async with AsyncSessionLocal() as session:
        if choice == "❌ Без группы":
            new_group = None
        else:
            grp = (await session.execute(
                select(Group).where(Group.name == choice)
            )).scalar()
            if not grp:
                return await message.answer("Нажмите кнопку с названием группы.")
            new_group = grp.id
        data = await state.get_data()
        poll_id = data["edit_poll_id"]
        await session.execute(
            Poll.__table__
            .update().where(Poll.id == poll_id)
            .values(group_id=new_group)
        )
        await session.commit()

    await message.answer("✅ Группа опроса обновлена.", reply_markup=ReplyKeyboardRemove())
    await state.finish()
    await return_to_admin_menu(message)

async def return_to_admin_menu(message: types.Message):
    """Отправляем кнопки админа."""
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(KeyboardButton("📊 Статистика"))
    kb.add(KeyboardButton("➕ Создать опрос"), KeyboardButton("🗑 Удалить опрос"))
    kb.add(KeyboardButton("✏️ Редактировать опрос"), KeyboardButton("📥 Экспорт результатов"))
    kb.add(KeyboardButton("👥 Управление пользователями"))
    await message.answer("Выберите действие:", reply_markup=kb)

def register_poll_edit(dp: Dispatcher):
    dp.register_message_handler(start_edit_poll, text="✏️ Редактировать опрос", state="*")
    dp.register_message_handler(choose_edit_poll, state=EditPollStates.choosing_poll)
    dp.register_message_handler(choose_edit_field, state=EditPollStates.choosing_field)
    dp.register_message_handler(process_edit_title, state=EditPollStates.editing_title)
    dp.register_message_handler(process_edit_target, state=EditPollStates.editing_target)
    dp.register_message_handler(process_edit_group, state=EditPollStates.editing_group)
