from aiogram import Dispatcher
from .poll_management import register_poll_management
from .poll_editor import register_poll_editor
from .poll_edit import register_poll_edit
from .start import cmd_start, add_users_to_db
from .poll_creation import register_poll_creation
from handlers.poll_take import StudentPollStates, choose_poll
from .poll_take import register_poll_take

from .poll_taking import (
    start_poll_taking,
    choose_poll,
    process_answer,
    send_next_question,
)

def register_handlers(dp: Dispatcher):
    # /start
    dp.register_message_handler(cmd_start, commands=["start"], state="*")
    # автодобавление в БД не регистрируется как хендлер, а вызывается в on_startup

    # Создание опросов
    register_poll_creation(dp)
    register_poll_management(dp)
    register_poll_editor(dp)
    # Прохождение опросов
    dp.register_message_handler(start_poll_taking, text="📋 Пройти опрос", state="*")
    dp.register_message_handler(choose_poll, state="PollTaking:choosing_poll")
    dp.register_message_handler(process_answer, state="PollTaking:answering_questions")
    dp.register_message_handler(choose_poll, state=StudentPollStates.choosing_poll)
    register_poll_take(dp)

