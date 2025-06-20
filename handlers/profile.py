# handlers/profile.py

from aiogram import types, Dispatcher
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import StatesGroup, State
from aiogram.types import ReplyKeyboardRemove, ReplyKeyboardMarkup, KeyboardButton
from sqlalchemy.future import select

from database import AsyncSessionLocal
from models import User, Group
from handlers.common import BACK, BACK_BTN
from handlers.back import return_to_main_menu


class Profile(StatesGroup):
    waiting_for_fio   = State()
    waiting_for_group = State()


async def ask_profile(message: types.Message, state: FSMContext):
    """
    Шаг 1: Просим ввести ФИО (три слова).
    """
    await Profile.waiting_for_fio.set()
    await message.answer(
        "Пожалуйста, введите Фамилию, Имя и Отчество (3 слова):",
        reply_markup=ReplyKeyboardRemove()
    )


async def process_fio(message: types.Message, state: FSMContext):
    """
    Шаг 2: Получили ФИО → сохранили в FSM и выводим клавиатуру групп.
    """
    text = message.text.strip()
    if text == BACK:
        await state.finish()
        return await return_to_main_menu(message)

    parts = text.split()
    if len(parts) != 3:
        return await message.answer(
            "Неверный формат. Введите ровно три слова для ФИО.",
            reply_markup=ReplyKeyboardRemove()
        )
    surname, name, patronymic = parts
    await state.update_data(surname=surname, name=name, patronymic=patronymic)

    # Динамически строим список групп
    async with AsyncSessionLocal() as session:
        rows = await session.execute(select(Group).order_by(Group.name))
        groups = rows.scalars().all()

    if not groups:
        await state.finish()
        return await message.answer(
            "Пока нет групп. Попросите админа создать группу.",
            reply_markup=BACK_BTN
        )

    kb = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    for g in groups:
        kb.add(KeyboardButton(g.name))
    kb.add(BACK_BTN)

    await Profile.waiting_for_group.set()
    await message.answer("Выберите, пожалуйста, свою группу:", reply_markup=kb)


async def process_group(message: types.Message, state: FSMContext):
    """
    Шаг 3: Проверяем нажатую группу и сохраняем ФИО+группу в БД.
    """
    grp_name = message.text.strip()
    if grp_name == BACK:
        await state.finish()
        return await return_to_main_menu(message)

    async with AsyncSessionLocal() as session:
        res = await session.execute(select(Group).where(Group.name == grp_name))
        grp = res.scalar_one_or_none()
        if not grp:
            return await message.answer(
                "Нажмите кнопку с названием вашей группы.",
                reply_markup=BACK_BTN
            )

        data = await state.get_data()
        await session.execute(
            User.__table__
            .update()
            .where(User.tg_id == message.from_user.id)
            .values(
                surname=data["surname"],
                name=data["name"],
                patronymic=data["patronymic"],
                group_id=grp.id
            )
        )
        await session.commit()

    await state.finish()
    # После регистрации студента заход в меню студентской роли
    return await return_to_main_menu(message)


def register_profile(dp: Dispatcher):
    dp.register_message_handler(ask_profile, commands=["register"], state="*")
    dp.register_message_handler(process_fio,   state=Profile.waiting_for_fio)
    dp.register_message_handler(process_group, state=Profile.waiting_for_group)
