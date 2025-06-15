# handlers/user_management.py

from aiogram import types, Dispatcher
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import StatesGroup, State
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from sqlalchemy.future import select
from sqlalchemy import delete, update

from database import AsyncSessionLocal
from models import User
from handlers.common import BACK, BACK_BTN
from handlers.start import _send_main_menu


class UserMgmtStates(StatesGroup):
    choosing_action    = State()
    adding_id          = State()
    choosing_new_role  = State()
    choosing_user      = State()
    confirming_delete  = State()
    editing_user_role  = State()


async def start_user_management(message: types.Message, state: FSMContext):
    tg = message.from_user.id
    async with AsyncSessionLocal() as s:
        me = (await s.execute(select(User).where(User.tg_id == tg))).scalar()
    if not me or me.role not in ("admin", "teacher"):
        return await message.answer("⛔ У вас нет прав.")
    # меню
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(KeyboardButton("📋 Список пользователей"))
    kb.add(KeyboardButton("➕ Добавить пользователя"), KeyboardButton("❌ Удалить пользователя"))
    kb.add(KeyboardButton("🔄 Изменить роль"), KeyboardButton("✅ Готово"))
    kb.add(BACK_BTN)
    await UserMgmtStates.choosing_action.set()
    await message.answer("👥 Управление пользователями:", reply_markup=kb)


async def process_user_action(message: types.Message, state: FSMContext):
    cmd = message.text.strip()
    tg = message.from_user.id
    async with AsyncSessionLocal() as s:
        me = (await s.execute(select(User).where(User.tg_id == tg))).scalar()

    # 1) список
    if cmd == "📋 Список пользователей":
        q = select(User)
        if me.role == "teacher":
            q = q.where(User.role != "admin")
        async with AsyncSessionLocal() as s2:
            users = (await s2.execute(q)).scalars().all()
        lines = [f"{u.id}. tg={u.tg_id} role={u.role}" for u in users] or ["⛔ Нет пользователей"]
        await message.answer("📝 Пользователи:\n" + "\n".join(lines), reply_markup=ReplyKeyboardRemove())
        return await _return_to_menu(message, state)

    # 2) добавить
    if cmd == "➕ Добавить пользователя":
        await UserMgmtStates.adding_id.set()
        return await message.answer("Введите TG ID нового пользователя:", reply_markup=ReplyKeyboardRemove())

    # 3) удалить
    if cmd == "❌ Удалить пользователя":
        q = select(User).where(User.role != "admin") if me.role == "teacher" else select(User)
        async with AsyncSessionLocal() as s2:
            users = (await s2.execute(q)).scalars().all()
        if not users:
            await message.answer("⛔ Нет пользователей для удаления.", reply_markup=ReplyKeyboardRemove())
            return await _return_to_menu(message, state)
        kb = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        for u in users:
            kb.add(KeyboardButton(f"{u.id}. {u.tg_id} ({u.role})"))
        kb.add(BACK_BTN)
        await state.update_data(user_action="delete")
        await UserMgmtStates.choosing_user.set()
        return await message.answer("Выберите пользователя для удаления:", reply_markup=kb)

    # 4) редактировать роль
    if cmd == "🔄 Изменить роль":
        q = select(User).where(User.role != "admin") if me.role == "teacher" else select(User)
        async with AsyncSessionLocal() as s2:
            users = (await s2.execute(q)).scalars().all()
        if not users:
            await message.answer("⛔ Нет пользователей для редактирования.", reply_markup=ReplyKeyboardRemove())
            return await _return_to_menu(message, state)
        kb = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        for u in users:
            kb.add(KeyboardButton(f"{u.id}. {u.tg_id} ({u.role})"))
        kb.add(BACK_BTN)
        await state.update_data(user_action="edit")
        await UserMgmtStates.choosing_user.set()
        return await message.answer("Выберите пользователя для смены роли:", reply_markup=kb)

    # 5) готово
    if cmd in ("✅ Готово", BACK):
        await state.finish()
        return await _send_main_menu(message, me.role)

    return await message.answer("Пожалуйста, используйте кнопки меню.")


async def process_add_id(message: types.Message, state: FSMContext):
    txt = message.text.strip()
    if not txt.isdigit():
        return await message.answer("Нужно ввести числовой TG ID.")
    await state.update_data(new_tg_id=int(txt))
    # выбираем роль
    kb = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    roles = ["teacher", "student"]  # админ нельзя добавить учителю
    kb.add(*(KeyboardButton(r) for r in roles))
    kb.add(BACK_BTN)
    await UserMgmtStates.choosing_new_role.set()
    return await message.answer("Выберите роль нового пользователя:", reply_markup=kb)


async def process_choose_role(message: types.Message, state: FSMContext):
    new_role = message.text.strip()
    data = await state.get_data()
    tg_new = data["new_tg_id"]

    if new_role not in ("admin", "teacher", "student"):
        return await message.answer("Выберите роль кнопкой.")
    # если текущий user — teacher, запретим admin
    tg = message.from_user.id
    async with AsyncSessionLocal() as s:
        me = (await s.execute(select(User).where(User.tg_id == tg))).scalar()
    if me.role == "teacher" and new_role == "admin":
        return await message.answer("⛔ Вы не можете назначить роль admin.", reply_markup=ReplyKeyboardRemove())

    async with AsyncSessionLocal() as s2:
        exists = (await s2.execute(select(User).where(User.tg_id == tg_new))).scalar()
        if exists:
            return await message.answer("⚠️ Пользователь уже есть в системе.", reply_markup=ReplyKeyboardRemove())
        s2.add(User(tg_id=tg_new, role=new_role))
        await s2.commit()

    await message.answer(f"✅ Пользователь {tg_new} создан как {new_role}.", reply_markup=ReplyKeyboardRemove())
    return await _return_to_menu(message, state)


async def process_choose_user(message: types.Message, state: FSMContext):
    txt = message.text.split(".")[0]
    if not txt.isdigit():
        return await message.answer("Нажмите на кнопку с номером.")
    uid = int(txt)
    data = await state.get_data()
    action = data.get("user_action")

    # Получаем target и проверяем admin
    async with AsyncSessionLocal() as s:
        target = (await s.execute(select(User).where(User.id == uid))).scalar()
    if not target:
        return await message.answer("Пользователь не найден.")
    # учитель не может трогать админа
    me_tg = message.from_user.id
    async with AsyncSessionLocal() as s2:
        me = (await s2.execute(select(User).where(User.tg_id == me_tg))).scalar()
    if me.role == "teacher" and target.role == "admin":
        return await message.answer("⛔ Вы не можете редактировать или удалять админа.", reply_markup=ReplyKeyboardRemove())

    await state.update_data(chosen_user_id=target.id)

    if action == "delete":
        kb = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        kb.add(KeyboardButton("✅ Да"), KeyboardButton("❌ Нет"), BACK_BTN)
        await UserMgmtStates.confirming_delete.set()
        return await message.answer(f"Удалить {target.tg_id} ({target.role})?", reply_markup=kb)

    if action == "edit":
        kb = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        # учитель не может назначить admin
        roles = ["teacher", "student"] if me.role=="teacher" else ["admin","teacher","student"]
        kb.add(*(KeyboardButton(r) for r in roles))
        kb.add(BACK_BTN)
        await UserMgmtStates.editing_user_role.set()
        return await message.answer(f"Новая роль для {target.tg_id}:", reply_markup=kb)


async def process_confirm_delete(message: types.Message, state: FSMContext):
    ans = message.text.strip()
    data = await state.get_data()
    uid  = data["chosen_user_id"]
    if ans == "✅ Да":
        async with AsyncSessionLocal() as s:
            await s.execute(delete(User).where(User.id == uid))
            await s.commit()
        await message.answer("✅ Удалено.", reply_markup=ReplyKeyboardRemove())
    else:
        await message.answer("❌ Отменено.", reply_markup=ReplyKeyboardRemove())
    return await _return_to_menu(message, state)


async def process_edit_user_role(message: types.Message, state: FSMContext):
    new_role = message.text.strip()
    if new_role not in ("admin","teacher","student"):
        return await message.answer("Выберите роль кнопкой.")
    data = await state.get_data()
    uid = data["chosen_user_id"]

    # опять проверяем, что мы не трогаем админа
    async with AsyncSessionLocal() as s1:
        target = (await s1.execute(select(User).where(User.id == uid))).scalar()
    if target.role == "admin" and new_role != "admin":
        return await message.answer("⛔ Вы не можете изменить роль админа.", reply_markup=ReplyKeyboardRemove())

    async with AsyncSessionLocal() as s2:
        await s2.execute(update(User).where(User.id==uid).values(role=new_role))
        await s2.commit()
    await message.answer(f"✅ Роль обновлена на {new_role}.", reply_markup=ReplyKeyboardRemove())
    return await _return_to_menu(message, state)


async def _return_to_menu(message: types.Message, state: FSMContext):
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(KeyboardButton("📋 Список пользователей"))
    kb.add(KeyboardButton("➕ Добавить пользователя"), KeyboardButton("❌ Удалить пользователя"))
    kb.add(KeyboardButton("🔄 Изменить роль"), KeyboardButton("✅ Готово"))
    kb.add(BACK_BTN)
    await UserMgmtStates.choosing_action.set()
    return await message.answer("👥 Управление пользователями:", reply_markup=kb)


def register_user_management(dp: Dispatcher):
    dp.register_message_handler(start_user_management,
                                text="👥 Управление пользователями", state="*")
    dp.register_message_handler(process_user_action,
                                state=UserMgmtStates.choosing_action)
    dp.register_message_handler(process_add_id,
                                state=UserMgmtStates.adding_id)
    dp.register_message_handler(process_choose_role,
                                state=UserMgmtStates.choosing_new_role)
    dp.register_message_handler(process_choose_user,
                                state=UserMgmtStates.choosing_user)
    dp.register_message_handler(process_confirm_delete,
                                state=UserMgmtStates.confirming_delete)
    dp.register_message_handler(process_edit_user_role,
                                state=UserMgmtStates.editing_user_role)
