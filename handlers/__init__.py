from aiogram import Dispatcher
from .back             import register_back
from .user_management  import register_user_management
from .start            import register_start_handlers, add_users_to_db
from .poll_creation    import register_poll_creation
from .poll_management  import register_poll_management
from .poll_editor      import register_poll_editor
from .poll_edit        import register_poll_edit
from .poll_take        import register_poll_take

def register_handlers(dp: Dispatcher):
    register_start_handlers(dp)
    register_poll_creation(dp)
    register_poll_management(dp)
    register_poll_editor(dp)
    register_poll_edit(dp)
    register_poll_take(dp)
    register_user_management(dp)
    register_back(dp)  # Регистрируем обработчик кнопки «Назад»


