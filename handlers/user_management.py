from aiogram import types, Dispatcher
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import StatesGroup, State
from aiogram.types import (
    ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
)
from sqlalchemy.future import select
from sqlalchemy import delete, update
from database import AsyncSessionLocal
from models import User
from handlers.start import _send_main_menu
from handlers.common import BACK_BTN

class UserMgmtStates(StatesGroup):
    choosing_action      = State()
    adding_id            = State()
    choosing_new_role    = State()
    choosing_user        = State()
    confirming_delete    = State()
    editing_user_role    = State()


async def start_user_management(message: types.Message, state: FSMContext):
    """Запускаем FSM управления пользователями."""
    # Проверим, что у нас admin или teacher
    tg = message.from_user.id
    async with AsyncSessionLocal() as s:
        user = (await s.execute(
            select(User).where(User.tg_id == tg)
        )).scalar()
    if not user or user.role not in ("admin", "teacher"):
        return await message.answer("⛔ У вас нет прав.")

    # Меню действий
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(KeyboardButton("📋 Список пользователей"))
    kb.add(KeyboardButton("➕ Добавить пользователя"), KeyboardButton("❌ Удалить пользователя"))
    kb.add(KeyboardButton("🔄 Изменить роль"), KeyboardButton("✅ Готово"))
    kb.add(BACK_BTN)  # Добавляем кнопку «Назад»
    await UserMgmtStates.choosing_action.set()
    await message.answer("👥 Управление пользователями: выберите действие", reply_markup=kb)


async def process_user_action(message: types.Message, state: FSMContext):
    """Обрабатываем выбор действия в меню управления."""
    cmd = message.text.strip()
    if cmd == "📋 Список пользователей":
        async with AsyncSessionLocal() as s:
            users = (await s.execute(select(User))).scalars().all()
        lines = []
        for u in users:
            grp = getattr(u, "group", None)
            grp_name = grp.name if grp else "-"
            lines.append(f"{u.id}. tg={u.tg_id} role={u.role} group={grp_name}")
        text = "📝 Пользователи:\n" + "\n".join(lines) if lines else "❌ Нет пользователей."
        await message.answer(text, reply_markup=ReplyKeyboardRemove())
        return await _return_to_menu(message, state)

    if cmd == "➕ Добавить пользователя":
        await UserMgmtStates.adding_id.set()
        await message.answer("Введите TG ID нового пользователя:", reply_markup=ReplyKeyboardRemove())
        return

    if cmd == "❌ Удалить пользователя":
        # Покажем список и предложим выбрать номер
        async with AsyncSessionLocal() as s:
            users = (await s.execute(select(User))).scalars().all()
        if not users:
            await message.answer("❌ Нет пользователей для удаления.", reply_markup=ReplyKeyboardRemove())
            return await _return_to_menu(message, state)

        kb = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        for u in users:
            kb.add(KeyboardButton(f"{u.id}. {u.tg_id} ({u.role})"))
        await state.update_data(user_action="delete")
        await UserMgmtStates.choosing_user.set()
        return await message.answer("Выберите пользователя для удаления:", reply_markup=kb)

    if cmd == "🔄 Изменить роль":
        # Список для выбора
        async with AsyncSessionLocal() as s:
            users = (await s.execute(select(User))).scalars().all()
        if not users:
            await message.answer("❌ Нет пользователей.", reply_markup=ReplyKeyboardRemove())
            return await _return_to_menu(message, state)

        kb = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        for u in users:
            kb.add(KeyboardButton(f"{u.id}. {u.tg_id} ({u.role})"))
        await state.update_data(user_action="edit")
        await UserMgmtStates.choosing_user.set()
        return await message.answer("Выберите пользователя для смены роли:", reply_markup=kb)

    if cmd == "✅ Готово":
        await state.finish()
        return await _send_main_menu(message, role="admin")

    # Если команда неизвестна
    return await message.answer("Пожалуйста, используйте кнопки меню.")


async def process_add_id(message: types.Message, state: FSMContext):
    """Вводим new TG ID."""
    txt = message.text.strip()
    if not txt.isdigit():
        return await message.answer("Нужно ввести числовой TG ID.")
    await state.update_data(new_tg_id=int(txt))

    # Выбираем роль
    kb = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    kb.add(KeyboardButton("admin"), KeyboardButton("teacher"), KeyboardButton("student"))
    await UserMgmtStates.choosing_new_role.set()
    await message.answer("Выберите роль нового пользователя:", reply_markup=kb)


async def process_choose_role(message: types.Message, state: FSMContext):
    """Выбрали роль для нового пользователя → добавляем."""
    role = message.text.strip()
    if role not in ("admin", "teacher", "student"):
        return await message.answer("Выберите роль кнопкой.")
    data = await state.get_data()
    tg_new = data["new_tg_id"]

    async with AsyncSessionLocal() as s:
        exists = (await s.execute(
            select(User).where(User.tg_id == tg_new)
        )).scalar()
        if exists:
            return await message.answer("⚠️ Пользователь уже существует.")
        s.add(User(tg_id=tg_new, role=role))
        await s.commit()

    await message.answer(f"✅ Пользователь {tg_new} создан с ролью {role}.", reply_markup=ReplyKeyboardRemove())
    return await _return_to_menu(message, state)


async def process_choose_user(message: types.Message, state: FSMContext):
    """Выбрали пользователя для удаления или редактирования."""
    txt = message.text.split(".")[0]
    if not txt.isdigit():
        return await message.answer("Нажмите кнопку с номером.")
    idx = int(txt)
    data = await state.get_data()
    action = data.get("user_action")

    async with AsyncSessionLocal() as s:
        user = (await s.execute(select(User).where(User.id == idx))).scalar()
    if not user:
        return await message.answer("Пользователь не найден.")

    await state.update_data(chosen_user_id=user.id)

    if action == "delete":
        kb = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        kb.add(KeyboardButton("✅ Да"), KeyboardButton("❌ Нет"))
        await UserMgmtStates.confirming_delete.set()
        return await message.answer(
            f"Удалить пользователя {user.tg_id} (role={user.role})?",
            reply_markup=kb
        )

    if action == "edit":
        kb = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        kb.add(KeyboardButton("admin"), KeyboardButton("teacher"), KeyboardButton("student"))
        await UserMgmtStates.editing_user_role.set()
        return await message.answer(
            f"Выберите новую роль для {user.tg_id} (текущая {user.role}):",
            reply_markup=kb
        )


async def process_confirm_delete(message: types.Message, state: FSMContext):
    """Подтверждаем или отменяем удаление пользователя."""
    ans = message.text.strip()
    data = await state.get_data()
    uid  = data["chosen_user_id"]

    if ans == "✅ Да":
        async with AsyncSessionLocal() as s:
            await s.execute(delete(User).where(User.id == uid))
            await s.commit()
        await message.answer("✅ Пользователь удалён.", reply_markup=ReplyKeyboardRemove())
    else:
        await message.answer("❌ Удаление отменено.", reply_markup=ReplyKeyboardRemove())

    return await _return_to_menu(message, state)


async def process_edit_user_role(message: types.Message, state: FSMContext):
    """Сохраняем новую роль выбранному пользователю."""
    new_role = message.text.strip()
    if new_role not in ("admin", "teacher", "student"):
        return await message.answer("Выберите роль кнопкой.")
    data = await state.get_data()
    uid  = data["chosen_user_id"]

    async with AsyncSessionLocal() as s:
        await s.execute(
            update(User)
            .where(User.id == uid)
            .values(role=new_role)
        )
        await s.commit()

    await message.answer(f"✅ Роль обновлена на {new_role}.", reply_markup=ReplyKeyboardRemove())
    return await _return_to_menu(message, state)


async def _return_to_menu(message: types.Message, state: FSMContext):
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(KeyboardButton("📋 Список пользователей"))
    kb.add(KeyboardButton("➕ Добавить пользователя"), KeyboardButton("❌ Удалить пользователя"))
    kb.add(KeyboardButton("🔄 Изменить роль"), KeyboardButton("✅ Готово"))
    await UserMgmtStates.choosing_action.set()
    return await message.answer("👥 Выберите действие:", reply_markup=kb)


def register_user_management(dp: Dispatcher):
    dp.register_message_handler(
        start_user_management,
        text="👥 Управление пользователями",
        state="*"
    )
    dp.register_message_handler(
        process_user_action,
        state=UserMgmtStates.choosing_action
    )
    dp.register_message_handler(
        process_add_id,
        state=UserMgmtStates.adding_id
    )
    dp.register_message_handler(
        process_choose_role,
        state=UserMgmtStates.choosing_new_role
    )
    dp.register_message_handler(
        process_choose_user,
        state=UserMgmtStates.choosing_user
    )
    dp.register_message_handler(
        process_confirm_delete,
        state=UserMgmtStates.confirming_delete
    )
    dp.register_message_handler(
        process_edit_user_role,
        state=UserMgmtStates.editing_user_role
    )
