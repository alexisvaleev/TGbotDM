from aiogram import Dispatcher

from .start            import register_start_handlers, add_users_to_db
from .poll_creation    import register_poll_creation
from .poll_management  import register_poll_management
from .poll_editor      import register_poll_editor
from .poll_edit        import register_poll_edit
from .poll_take        import register_poll_take

def register_handlers(dp: Dispatcher):
    # 1) /start и выбор группы
    register_start_handlers(dp)

    # 2) Админские возможности
    register_poll_creation(dp)
    register_poll_management(dp)
    register_poll_editor(dp)
    register_poll_edit(dp)

    # 3) Студенты/учителя: проходить опрос
    register_poll_take(dp)
