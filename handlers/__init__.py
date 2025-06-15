from aiogram import Dispatcher
from .back             import register_back
from .start            import register_start_handlers
from .poll_creation    import register_poll_creation
from .poll_management  import register_poll_management
from .poll_editor      import register_poll_editor
from .poll_edit        import register_poll_edit
from .poll_take        import register_poll_take
from .poll_statistics  import register_poll_statistics
from .user_management import add_users_to_db, register_user_management

def register_handlers(dp: Dispatcher):
    register_back(dp)
    register_start_handlers(dp)
    register_poll_creation(dp)
    register_poll_management(dp)
    register_poll_editor(dp)
    register_poll_edit(dp)
    register_poll_take(dp)
    register_poll_statistics(dp)
    register_user_management(dp)
