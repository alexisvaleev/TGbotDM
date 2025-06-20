from aiogram import types, Dispatcher
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import StatesGroup, State
from aiogram.types import ReplyKeyboardMarkup, ReplyKeyboardRemove, KeyboardButton

from sqlalchemy.future import select
from sqlalchemy import update, insert

from database import AsyncSessionLocal
from models import User
from .common import BACK, BACK_BTN
from .back import return_to_main_menu
from config import load_config

class UserMgmtStates(StatesGroup):
    waiting_for_id   = State()
    waiting_for_role = State()

async def cmd_view_users(message: types.Message):
    async with AsyncSessionLocal() as s:
        me = (await s.execute(
            select(User).where(User.tg_id==message.from_user.id)
        )).scalar_one_or_none()
        if not me or me.role not in ("admin","teacher"):
            return await message.answer("⛔ У вас нет прав.")
        users = (await s.execute(select(User))).scalars().all()
    text = "\n".join(
        f"{u.tg_id}: {u.surname or '-'} {u.name or '-'} ({u.role})"
        for u in users
    ) or "🚫 Нет пользователей."
    await message.answer(text, reply_markup=BACK_BTN)

async def start_add_user(message: types.Message, state: FSMContext):
    async with AsyncSessionLocal() as s:
        me = (await s.execute(
            select(User).where(User.tg_id==message.from_user.id)
        )).scalar_one_or_none()
    if not me or me.role not in ("admin","teacher"):
        return await message.answer("⛔ У вас нет прав.")
    await state.update_data(initiator=me.role)
    await UserMgmtStates.waiting_for_id.set()
    await message.answer("Введите Telegram ID пользователя:", reply_markup=ReplyKeyboardRemove())

async def process_user_id(message: types.Message, state: FSMContext):
    txt = message.text.strip()
    if txt == BACK:
        await state.finish()
        return await return_to_main_menu(message)
    if not txt.isdigit():
        return await message.answer("⛔ Введите числовой ID.")
    await state.update_data(new_id=int(txt))
    initiator = (await state.get_data())["initiator"]
    kb = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    if initiator=="admin":
        kb.add("admin")
    kb.add("teacher","student").add(BACK)
    await UserMgmtStates.waiting_for_role.set()
    await message.answer("Выберите роль для пользователя:", reply_markup=kb)

async def process_user_role(message: types.Message, state: FSMContext):
    txt = message.text.strip().lower()
    if txt == BACK:
        await state.finish()
        return await return_to_main_menu(message)
    if txt not in ("admin","teacher","student"):
        return await message.answer("⛔ Выберите роль кнопкой.", reply_markup=BACK_BTN)
    new_id = (await state.get_data())["new_id"]
    async with AsyncSessionLocal() as s:
        ex = (await s.execute(
            select(User).where(User.tg_id==new_id)
        )).scalar_one_or_none()
        if ex:
            await s.execute(update(User).where(User.tg_id==new_id).values(role=txt))
            msg = f"✅ Роль пользователя {new_id} обновлена на «{txt}»."
        else:
            await s.execute(insert(User).values(
                tg_id=new_id, role=txt, surname=None, name=None, patronymic=None
            ))
            msg = f"✅ Пользователь {new_id} добавлен с ролью «{txt}»."
        await s.commit()
    await state.finish()
    await message.answer(msg, reply_markup=BACK_BTN)
    return await return_to_main_menu(message)

async def add_users_to_db():
    """Seed ADMIN_IDS, TEACHER_IDS, STUDENT_IDS из config."""
    cfg = load_config()
    async with AsyncSessionLocal() as s:
        for tg in cfg.ADMIN_IDS:
            ex = (await s.execute(select(User).where(User.tg_id==tg))).scalar_one_or_none()
            if ex:
                await s.execute(update(User).where(User.tg_id==tg).values(role="admin"))
            else:
                s.add(User(tg_id=tg, role="admin"))
        for tg in cfg.TEACHER_IDS:
            ex = (await s.execute(select(User).where(User.tg_id==tg))).scalar_one_or_none()
            if ex:
                await s.execute(update(User).where(User.tg_id==tg).values(role="teacher"))
            else:
                s.add(User(tg_id=tg, role="teacher"))
        for tg in cfg.STUDENT_IDS:
            ex = (await s.execute(select(User).where(User.tg_id==tg))).scalar_one_or_none()
            if ex:
                await s.execute(update(User).where(User.tg_id==tg).values(role="student"))
            else:
                s.add(User(tg_id=tg, role="student"))
        await s.commit()

def register_user_management(dp: Dispatcher):
    dp.register_message_handler(start_delete_user,
                                text="🗑 Удалить пользователя", state=None)
    dp.register_message_handler(process_user_deletion,
                                state="waiting_for_deletion")
    dp.register_message_handler(cmd_view_users,
                                text="Просмотр пользователей", state=None)
    dp.register_message_handler(start_add_user,
                                text=["➕ Добавить пользователя","✏️ Редактировать пользователя"],
                                state=None)
    dp.register_message_handler(process_user_id,
                                state=UserMgmtStates.waiting_for_id)
    dp.register_message_handler(process_user_role,
                                state=UserMgmtStates.waiting_for_role)
# ───── Удаление пользователей ─────────────────────────────────────

async def start_delete_user(message: types.Message, state: FSMContext):
    tg = message.from_user.id
    async with AsyncSessionLocal() as s:
        me = (await s.execute(select(User).where(User.tg_id == tg))).scalar_one_or_none()
    if not me or me.role not in ("admin", "teacher"):
        return await message.answer("⛔ У вас нет прав.")

    await message.answer("Введите Telegram ID пользователя для удаления:", reply_markup=BACK_BTN)
    await state.set_state("waiting_for_deletion")

# ─── Удаление пользователей ─────────────────────────────────────

async def start_delete_user(message: types.Message, state: FSMContext):
    tg = message.from_user.id
    async with AsyncSessionLocal() as s:
        me = (await s.execute(select(User).where(User.tg_id == tg))).scalar_one_or_none()
    if not me or me.role not in ("admin", "teacher"):
        return await message.answer("⛔ У вас нет прав.")

    await message.answer("Введите Telegram ID пользователя для удаления:", reply_markup=BACK_BTN)
    await state.set_state("waiting_for_deletion")

async def process_user_deletion(message: types.Message, state: FSMContext):
    txt = message.text.strip()
    if txt == BACK:
        await state.finish()
        return await return_to_main_menu(message)

    if not txt.isdigit():
        return await message.answer("⛔ Введите числовой ID.")

    del_id = int(txt)
    async with AsyncSessionLocal() as s:
        user = (await s.execute(select(User).where(User.tg_id == del_id))).scalar_one_or_none()
        if not user:
            return await message.answer(f"🚫 Пользователь {del_id} не найден.", reply_markup=BACK_BTN)
        await s.delete(user)
        await s.commit()

    await state.finish()
    await message.answer(f"✅ Пользователь {del_id} удалён.", reply_markup=BACK_BTN)
    return await return_to_main_menu(message)
