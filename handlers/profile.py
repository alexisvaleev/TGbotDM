from aiogram import types, Dispatcher
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import StatesGroup, State
from sqlalchemy.future import select

from database import AsyncSessionLocal
from models import User, Group
from .common import BACK, BACK_BTN
from .back   import return_to_main_menu

class ProfileStates(StatesGroup):
    waiting_surname    = State()
    waiting_name       = State()
    waiting_patronymic = State()
    waiting_group      = State()

async def ask_profile(message: types.Message, state: FSMContext):
    await state.finish()
    await ProfileStates.waiting_surname.set()
    await message.answer("Введите фамилию:", reply_markup=BACK_BTN)

async def process_surname(message: types.Message, state: FSMContext):
    txt = message.text.strip()
    if txt == BACK:
        await state.finish()
        return await return_to_main_menu(message)
    await state.update_data(surname=txt)
    await ProfileStates.next()
    await message.answer("Введите имя:", reply_markup=BACK_BTN)

async def process_name(message: types.Message, state: FSMContext):
    txt = message.text.strip()
    if txt == BACK:
        await state.finish()
        return await return_to_main_menu(message)
    await state.update_data(name=txt)
    await ProfileStates.next()
    await message.answer("Введите отчество:", reply_markup=BACK_BTN)

async def process_patronymic(message: types.Message, state: FSMContext):
    txt = message.text.strip()
    if txt == BACK:
        await state.finish()
        return await return_to_main_menu(message)
    await state.update_data(patronymic=txt)
    # кнопки групп
    async with AsyncSessionLocal() as s:
        groups = (await s.execute(select(Group))).scalars().all()
    kb = BACK_BTN.copy()
    for g in groups:
        kb.insert(0, [g.name])
    await ProfileStates.next()
    await message.answer("Выберите группу:", reply_markup=kb)

async def process_group(message: types.Message, state: FSMContext):
    txt = message.text.strip()
    if txt == BACK:
        await state.finish()
        return await return_to_main_menu(message)
    data = await state.get_data()
    async with AsyncSessionLocal() as s:
        u = (await s.execute(
            select(User).where(User.tg_id==message.from_user.id)
        )).scalar_one_or_none()
        u.surname    = data["surname"]
        u.name       = data["name"]
        u.patronymic = data["patronymic"]
        grp = (await s.execute(
            select(Group).where(Group.name==txt)
        )).scalar_one_or_none()
        if grp: u.group_id = grp.id
        await s.commit()
    await state.finish()
    await message.answer("✅ Профиль сохранён.", reply_markup=BACK_BTN)
    return await return_to_main_menu(message)

def register_profile(dp: Dispatcher):
    dp.register_message_handler(ask_profile,
                                commands=["profile"], state="*")
    dp.register_message_handler(process_surname,
                                state=ProfileStates.waiting_surname)
    dp.register_message_handler(process_name,
                                state=ProfileStates.waiting_name)
    dp.register_message_handler(process_patronymic,
                                state=ProfileStates.waiting_patronymic)
    dp.register_message_handler(process_group,
                                state=ProfileStates.waiting_group)
