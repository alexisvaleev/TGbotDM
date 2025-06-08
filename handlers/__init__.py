from aiogram import Dispatcher

from .start import cmd_start
from .poll_creation import (
    PollCreation,
    start_poll_creation,
    register_poll_creation,
)
from .poll_taking import (
    PollTaking,
    start_poll_taking,
    choose_poll,
    send_next_question,
    process_answer,
)

def register_handlers(dp: Dispatcher):
    dp.register_message_handler(cmd_start, commands=["start"], state="*")

    # Регистрация хендлеров создания опроса
    register_poll_creation(dp)

    # Хендлеры прохождения опросов
    dp.register_message_handler(start_poll_taking, text="📋 Пройти опрос", state="*")
    dp.register_message_handler(choose_poll, state=PollTaking.choosing_poll)
    dp.register_message_handler(process_answer, state=PollTaking.answering_questions)
