from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

# Текст кнопки «Назад»
BACK = "🔙 Назад"

# Клавиатура с одной кнопкой «Назад»
BACK_BTN = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(BACK)]],
    resize_keyboard=True,
    one_time_keyboard=True
)
