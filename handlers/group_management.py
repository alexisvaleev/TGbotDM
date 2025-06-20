from sqlalchemy.future import select
from aiogram import Dispatcher
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from database import AsyncSessionLocal
from models import Group
from handlers.common import BACK, BACK_BTN
from handlers.back   import return_to_main_menu
from aiogram import types

# в начале файла уже должны быть импорты aiogram, FSMContext и т. п.

async def start_group_creation(message: types.Message, state):
    # TODO: ваш код создания группы
    await message.answer("Здесь запустится FSM создания группы")

async def start_group_assignment(message: types.Message, state):
    # TODO: ваш код назначения пользователя в группу
    await message.answer("Здесь запустится FSM назначения пользователя в группу")

def register_group_management(dp: Dispatcher):
    dp.register_message_handler(start_group_creation,
                                text="➕ Создать группу", state="*")
    dp.register_message_handler(start_group_assignment,
                                text="🔀 Назначить группу", state="*")
    # … остальные регистрации FSM …


async def seed_groups():
    """
    Сеем группы из .env → GROUP_NAMES
    """
    from config import load_config
    cfg = load_config()
    if not cfg.GROUP_NAMES:
        return

    async with AsyncSessionLocal() as s:
        existing = {g.name for g in (await s.execute(select(Group))).scalars().all()}
        for name in cfg.GROUP_NAMES:
            if name not in existing:
                s.add(Group(name=name))
        await s.commit()

# ↓ ниже ваши хэндлеры для создания/назначения группы
def register_group_management(dp: Dispatcher):
    # dp.register_message_handler(start_group_creation, text="➕ Создать группу")
    # dp.register_message_handler(process_group_name, state=GroupCreationStates.name)
    # ...
    pass
