from aiogram import types, Dispatcher
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import StatesGroup, State
from aiogram.types import ReplyKeyboardMarkup

from sqlalchemy.future import select
from sqlalchemy import update

from database import AsyncSessionLocal
from models import Group, User
from .common import BACK, BACK_BTN
from .back   import return_to_main_menu

class GroupStates(StatesGroup):
    waiting_name     = State()
    waiting_user_id  = State()
    waiting_group_id = State()

async def seed_groups():
    from config import load_config
    cfg = load_config()
    if not cfg.GROUP_NAMES:
        return
    async with AsyncSessionLocal() as s:
        existing = {g.name for g in (await s.execute(select(Group))).scalars()}
        for name in cfg.GROUP_NAMES:
            if name not in existing:
                s.add(Group(name=name))
        await s.commit()

async def start_group_creation(message: types.Message, state: FSMContext):
    await GroupStates.waiting_name.set()
    await message.answer("Введите название новой группы:", reply_markup=BACK_BTN)

async def process_group_name(message: types.Message, state: FSMContext):
    txt = message.text.strip()
    if txt == BACK:
        await state.finish()
        return await return_to_main_menu(message)
    async with AsyncSessionLocal() as s:
        s.add(Group(name=txt))
        await s.commit()
    await state.finish()
    await message.answer(f"✅ Группа «{txt}» создана.", reply_markup=BACK_BTN)
    return await return_to_main_menu(message)

async def start_group_assignment(message: types.Message, state: FSMContext):
    await GroupStates.waiting_user_id.set()
    await message.answer("Введите Telegram ID пользователя:", reply_markup=BACK_BTN)

async def process_group_user(message: types.Message, state: FSMContext):
    txt = message.text.strip()
    if txt == BACK:
        await state.finish()
        return await return_to_main_menu(message)
    if not txt.isdigit():
        return await message.answer("⛔ Введите числовой ID.", reply_markup=BACK_BTN)
    await state.update_data(user_id=int(txt))
    # предложим список групп
    async with AsyncSessionLocal() as s:
        groups = (await s.execute(select(Group))).scalars().all()
    kb = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    for g in groups:
        kb.add(g.name)
    kb.add(BACK)
    await GroupStates.waiting_group_id.set()
    await message.answer("Выберите группу:", reply_markup=kb)

async def process_group_select(message: types.Message, state: FSMContext):
    txt = message.text.strip()
    if txt == BACK:
        await state.finish()
        return await return_to_main_menu(message)
    data = await state.get_data()
    user_id = data["user_id"]
    async with AsyncSessionLocal() as s:
        grp = (await s.execute(
            select(Group).where(Group.name==txt)
        )).scalar_one_or_none()
        user = (await s.execute(
            select(User).where(User.tg_id==user_id)
        )).scalar_one_or_none()
        if not grp or not user:
            return await message.answer("⛔ Неверный выбор.", reply_markup=BACK_BTN)
        await s.execute(
            update(User).where(User.tg_id==user_id).values(group_id=grp.id)
        )
        await s.commit()
    await state.finish()
    await message.answer(f"✅ Пользователь {user_id} назначен в группу «{txt}».",
                         reply_markup=BACK_BTN)
    return await return_to_main_menu(message)

def register_group_management(dp: Dispatcher):
    dp.register_message_handler(start_group_creation,
                                text="➕ Создать группу", state=None)
    dp.register_message_handler(process_group_name,
                                state=GroupStates.waiting_name)
    dp.register_message_handler(start_group_assignment,
                                text="🔀 Назначить группу", state=None)
    dp.register_message_handler(process_group_user,
                                state=GroupStates.waiting_user_id)
    dp.register_message_handler(process_group_select,
                                state=GroupStates.waiting_group_id)
