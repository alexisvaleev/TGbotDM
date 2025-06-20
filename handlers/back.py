from aiogram import types

async def return_to_main_menu(message: types.Message):
    """
    Универсальный возврат в главное меню.
    """
    from .menu import send_main_menu
    return await send_main_menu(message)
