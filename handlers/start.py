# handlers/start.py

from aiogram import types, Dispatcher
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import StatesGroup, State
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from sqlalchemy.future import select

from database import AsyncSessionLocal
from models import User, Group
from config import ADMIN_IDS, TEACHER_IDS, STUDENT_IDS


class SettingGroup(StatesGroup):
    waiting_for_group = State()


async def add_users_to_db(dp: Dispatcher):
    async with AsyncSessionLocal() as session:
        users = (await session.execute(select(User))).scalars().all()
        for u in users:
            # определяем актуальную роль по .env
            if u.tg_id in ADMIN_IDS:
                real_role = "admin"
            elif u.tg_id in TEACHER_IDS:
                real_role = "teacher"
            elif u.tg_id in STUDENT_IDS:
                real_role = "student"
            else:
                real_role = u.role  # или "unknown"
            # если не совпадает — обновляем
            if u.role != real_role:
                await session.execute(
                    User.__table__.update()
                    .where(User.id == u.id)
                    .values(role=real_role)
                )
        # теперь заводим новых, как раньше
        existing_ids = {u.tg_id for u in users}
        all_ids = set(ADMIN_IDS) | set(TEACHER_IDS) | set(STUDENT_IDS)
        for tg in all_ids - existing_ids:
            role = ("admin" if tg in ADMIN_IDS else
                    "teacher" if tg in TEACHER_IDS else
                    "student")
            session.add(User(tg_id=tg, role=role))
        await session.commit()



async def cmd_start(message: types.Message, state: FSMContext):
    """/start — регистрируем пользователя, спрашиваем группу или рисуем меню."""
    await state.finish()
    tg = message.from_user.id

    # Убедимся, что пользователь в БД
    async with AsyncSessionLocal() as session:
        user = (await session.execute(select(User).where(User.tg_id == tg))).scalar()
        if not user:
            # роль из .env
            if   tg in ADMIN_IDS:   role = "admin"
            elif tg in TEACHER_IDS: role = "teacher"
            elif tg in STUDENT_IDS: role = "student"
            else:                   role = "unknown"
            user = User(tg_id=tg, role=role)
            session.add(user)
            await session.commit()

    # Если учитель/студент и нет группы — спрашиваем группу
    if user.role in ("teacher", "student") and not user.group_id:
        async with AsyncSessionLocal() as session:
            groups = (await session.execute(select(Group))).scalars().all()
        kb = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        for g in groups:
            kb.add(KeyboardButton(g.name))
        await SettingGroup.waiting_for_group.set()
        return await message.answer("Пожалуйста, выберите вашу группу:", reply_markup=kb)

    # Иначе сразу меню
    return await _send_main_menu(message, user.role)


async def process_group_choice(message: types.Message, state: FSMContext):
    """Сохраняем выбранную группу и рисуем меню."""
    tg = message.from_user.id
    choice = message.text.strip()

    async with AsyncSessionLocal() as session:
        grp = (await session.execute(
            select(Group).where(Group.name == choice)
        )).scalar()
        if not grp:
            return await message.answer("Нажмите кнопку с названием вашей группы.")
        # обновляем пользователя
        await session.execute(
            User.__table__.update()
            .where(User.tg_id == tg)
            .values(group_id=grp.id)
        )
        await session.commit()

    await state.finish()
    await message.answer(f"Группа «{grp.name}» сохранена.", reply_markup=ReplyKeyboardRemove())

    # повторно читаем роль, чтобы нарисовать нужное меню
    async with AsyncSessionLocal() as session2:
        user = (await session2.execute(select(User).where(User.tg_id == tg))).scalar()
    return await _send_main_menu(message, user.role)


async def _send_main_menu(message: types.Message, role: str):
    """
    Рисует главное меню в зависимости от роли:
      - admin   → кнопки создания/удаления/редактирования/экспорта
      - teacher → кнопки создания и прохождения опроса
      - student → кнопка прохождения опроса
    """
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    if role == "admin":
        kb.add(KeyboardButton("➕ Создать опрос"), KeyboardButton("🗑 Удалить опрос"))
        kb.add(KeyboardButton("✏️ Редактировать опрос"), KeyboardButton("📥 Экспорт результатов"))
    elif role == "teacher":
        kb.add(KeyboardButton("➕ Создать опрос"), KeyboardButton("📋 Пройти опрос"))
    elif role == "student":
        kb.add(KeyboardButton("📋 Пройти опрос"))
    else:
        return await message.answer("⛔ У вас нет прав для использования бота.")

    return await message.answer("Выберите действие:", reply_markup=kb)


def register_start_handlers(dp: Dispatcher):
    dp.register_message_handler(cmd_start, commands=["start"], state="*")
    dp.register_message_handler(process_group_choice, state=SettingGroup.waiting_for_group)
