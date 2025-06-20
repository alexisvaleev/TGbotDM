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
    # 1) /start + проверка в БД
    register_start_handlers(dp)

    # 2) FSM профиля (ФИО/группа)
    register_profile(dp)

    # 3) Управление пользователями (admin/teacher)
    register_user_management(dp)

    # 4) Группы: создание и назначение
    register_group_management(dp)

    # 5) Опросы: создание, редактирование, удаление
    register_poll_creation(dp)
    register_poll_editor(dp)
    register_poll_management(dp)

    # 6) Статистика
    register_poll_statistics(dp)

    # 7) Прохождение опроса (students)
    register_poll_take(dp)

    # 8) Меню (route_menu + send_main_menu)
    register_menu(dp)
