from aiogram import types

async def return_to_main_menu(message: types.Message):
    """
    Можно использовать внутри FSM, чтобы выйти обратно в /start-меню.
    """
    from handlers.menu import send_main_menu
    return await send_main_menu(message)
