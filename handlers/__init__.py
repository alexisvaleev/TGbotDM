# handlers/__init__.py

from aiogram import Dispatcher
from .profile            import register_profile
from .start              import register_start_handlers
from .poll_creation      import register_poll_creation
from .poll_take          import register_poll_take
from .poll_management    import register_poll_management
from .poll_editor        import register_poll_editor
from .poll_statistics    import register_poll_statistics
from .user_management    import register_user_management
from .group_management   import register_group_management
from .back     import return_to_main_menu     # не регистрируется, это утилита

def register_handlers(dp: Dispatcher):
    register_profile(dp)
    register_start_handlers(dp)

    register_poll_creation(dp)
    register_poll_management(dp)
    register_poll_editor(dp)
    register_poll_take(dp)
    register_poll_statistics(dp)
    register_user_management(dp)
    register_group_management(dp)

