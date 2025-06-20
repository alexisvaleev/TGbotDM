from aiogram import Dispatcher

from .start              import register_start_handlers
from .profile            import register_profile
from .user_management    import register_user_management
from .group_management   import register_group_management
from .poll_creation      import register_poll_creation
from .poll_editor        import register_poll_editor
from .poll_management    import register_poll_management
from .poll_statistics    import register_poll_statistics
from .poll_take          import register_poll_take
from .menu               import register_menu

def register_handlers(dp: Dispatcher):
    register_start_handlers(dp)
    register_profile(dp)
    register_user_management(dp)
    register_group_management(dp)
    register_poll_creation(dp)
    register_poll_editor(dp)
    register_poll_management(dp)
    register_poll_statistics(dp)
    register_poll_take(dp)
    register_menu(dp)
