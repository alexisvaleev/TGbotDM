from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

BACK = "🔙 Назад"
BACK_BTN = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(BACK)]],
    resize_keyboard=True,
    one_time_keyboard=True
)
