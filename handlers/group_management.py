# handlers/group_management.py

from aiogram import types, Dispatcher
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import StatesGroup, State
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from sqlalchemy.future import select

from database import AsyncSessionLocal
from models import Group, User
from handlers.common import BACK, BACK_BTN
from handlers.back import return_to_main_menu


class GroupMgmt(StatesGroup):
    creating_group   = State()
    choosing_user    = State()
    choosing_new_grp = State()


async def start_group_creation(message: types.Message, state: FSMContext):
    """➕ Создать группу (admin или teacher)."""
    await state.finish()
    tg = message.from_user.id
    async with AsyncSessionLocal() as s:
        me = (await s.execute(select(User).where(User.tg_id == tg))).scalar_one_or_none()
    if not me or me.role not in ("admin", "teacher"):
        return await message.answer("⛔ У вас нет прав.")

    await GroupMgmt.creating_group.set()
    await message.answer("Введите название новой группы:", reply_markup=ReplyKeyboardRemove())


async def process_group_name(message: types.Message, state: FSMContext):
    """Обработка названия группы и её создание."""
    name = message.text.strip()
    if name == BACK:
        await state.finish()
        return await return_to_main_menu(message)

    async with AsyncSessionLocal() as s:
        exists = (await s.execute(select(Group).where(Group.name == name))).scalar_one_or_none()
        if exists:
            await message.answer("⚠️ Такая группа уже есть.", reply_markup=ReplyKeyboardRemove())
            await state.finish()
            return await return_to_main_menu(message)

        s.add(Group(name=name))
        await s.commit()

    await message.answer(f"✅ Группа «{name}» создана.", reply_markup=ReplyKeyboardRemove())
    await state.finish()
    return await return_to_main_menu(message)


async def start_group_assignment(message: types.Message, state: FSMContext):
    """🔀 Назначить группу (admin или teacher)."""
    await state.finish()
    tg = message.from_user.id
    async with AsyncSessionLocal() as s:
        me = (await s.execute(select(User).where(User.tg_id == tg))).scalar_one_or_none()
    if not me or me.role not in ("admin", "teacher"):
        return await message.answer("⛔ У вас нет прав.")

    async with AsyncSessionLocal() as s2:
        studs = (await s2.execute(select(User).where(User.role == "student"))).scalars().all()
    if not studs:
        await message.answer("⛔ Нет студентов.", reply_markup=BACK_BTN)
        return

    kb = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    for u in studs:
        parts = [
            getattr(u, "surname", ""),
            getattr(u, "name", ""),
            getattr(u, "patronymic", "")
        ]
        fullname = " ".join(filter(None, parts)) or f"<{u.tg_id}>"
        kb.add(KeyboardButton(f"{u.id}. {fullname}"))
    kb.add(BACK_BTN)

    await state.update_data(action="assign")
    await GroupMgmt.choosing_user.set()
    await message.answer("Выберите студента:", reply_markup=kb)


async def process_choose_user(message: types.Message, state: FSMContext):
    """Получили ID студента — теперь список групп."""
    txt = message.text.split(".", 1)[0].strip()
    if txt == BACK:
        await state.finish()
        return await return_to_main_menu(message)
    if not txt.isdigit():
        return await message.answer("Нажмите кнопку со студентом.")

    uid = int(txt)
    data = await state.get_data()
    if data.get("action") != "assign":
        await state.finish()
        return await return_to_main_menu(message)

    async with AsyncSessionLocal() as s:
        target = (await s.execute(
            select(User).where(User.id == uid, User.role == "student")
        )).scalar_one_or_none()
    if not target:
        await message.answer("Студент не найден.", reply_markup=ReplyKeyboardRemove())
        await state.finish()
        return await return_to_main_menu(message)

    async with AsyncSessionLocal() as s2:
        grps = (await s2.execute(select(Group))).scalars().all()
    kb = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    for g in grps:
        kb.add(KeyboardButton(g.name))
    kb.add(BACK_BTN)

    await state.update_data(chosen_user=uid)
    await GroupMgmt.choosing_new_grp.set()
    await message.answer("Теперь выберите новую группу:", reply_markup=kb)


async def process_choose_group(message: types.Message, state: FSMContext):
    """Сохраняем выбранную группу студенту."""
    grp_name = message.text.strip()
    if grp_name == BACK:
        await state.finish()
        return await return_to_main_menu(message)

    data = await state.get_data()
    uid  = data.get("chosen_user")

    async with AsyncSessionLocal() as s:
        grp = (await s.execute(select(Group).where(Group.name == grp_name))).scalar_one_or_none()
        if not grp:
            return await message.answer("Нажмите кнопку с названием группы.")

        await s.execute(
            User.__table__.update()
            .where(User.id == uid)
            .values(group_id=grp.id)
        )
        await s.commit()

    await message.answer(f"✅ Студенту назначена группа «{grp.name}».", reply_markup=ReplyKeyboardRemove())
    await state.finish()
    return await return_to_main_menu(message)


def register_group_management(dp: Dispatcher):
    dp.register_message_handler(
        start_group_creation, text="➕ Создать группу", state="*"
    )
    dp.register_message_handler(
        process_group_name, state=GroupMgmt.creating_group
    )

    dp.register_message_handler(
        start_group_assignment, text="🔀 Назначить группу", state="*"
    )
    dp.register_message_handler(
        process_choose_user, state=GroupMgmt.choosing_user
    )
    dp.register_message_handler(
        process_choose_group, state=GroupMgmt.choosing_new_grp
    )
