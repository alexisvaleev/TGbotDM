# handlers/poll_editor.py

from aiogram import types, Dispatcher
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import StatesGroup, State
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from sqlalchemy.future import select
from sqlalchemy import delete

from database import AsyncSessionLocal
from models import User, Poll, Question, Answer, Group
from handlers.common import BACK, BACK_BTN
from handlers.back import return_to_main_menu


class PollEditorStates(StatesGroup):
    choosing_poll         = State()
    choosing_mode         = State()
    choosing_field        = State()
    editing_title         = State()
    editing_target        = State()
    editing_group         = State()
    choosing_question     = State()
    action_menu           = State()
    editing_q_text        = State()
    adding_option         = State()
    choosing_opt_to_del   = State()
    confirming_opt_delete = State()


# ——— Шаг 1: выбор опроса —————————————————————————————
async def start_poll_editor(message: types.Message, state: FSMContext):
    await state.finish()
    tg = message.from_user.id
    async with AsyncSessionLocal() as s:
        me = (await s.execute(
            select(User).where(User.tg_id == tg)
        )).scalar_one_or_none()
        if not me or me.role not in ("admin", "teacher"):
            return await message.answer("⛔ Только админ или преподаватель может редактировать опросы.")
        polls = (await s.execute(select(Poll))).scalars().all()

    if not polls:
        return await message.answer("🚫 Нет опросов для редактирования.", reply_markup=BACK_BTN)

    kb = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    for i, p in enumerate(polls, 1):
        kb.add(KeyboardButton(f"{i}. {p.title}"))
    kb.add(BACK)

    await state.update_data(poll_ids=[p.id for p in polls])
    await PollEditorStates.choosing_poll.set()
    await message.answer("✏️ Выберите опрос для редактирования:", reply_markup=kb)


# ——— Шаг 2: подтвердить или выйти —————————————————————————
async def choose_poll(message: types.Message, state: FSMContext):
    txt = message.text.strip()
    if txt == BACK:
        await state.finish()
        return await return_to_main_menu(message)

    data = await state.get_data()
    poll_ids = data.get("poll_ids", [])
    idx_part = txt.split(".", 1)[0]
    if not idx_part.isdigit():
        return await message.answer("Пожалуйста, нажмите кнопку с номером опроса.", reply_markup=BACK_BTN)
    idx = int(idx_part) - 1
    if idx < 0 or idx >= len(poll_ids):
        return await message.answer("Неверный номер опроса.", reply_markup=BACK_BTN)

    await state.update_data(edit_poll_id=poll_ids[idx])

    kb = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    kb.add(KeyboardButton("🔤 Параметры опроса"))
    kb.add(KeyboardButton("📝 Вопросы"))
    kb.add(KeyboardButton("❌ Готово"))
    kb.add(BACK)

    await PollEditorStates.choosing_mode.set()
    await message.answer("Что будем править?", reply_markup=kb)


# ——— Шаг 3: режим редактирования —————————————————————————
async def choose_mode(message: types.Message, state: FSMContext):
    txt = message.text.strip()
    if txt == BACK:
        await state.finish()
        return await return_to_main_menu(message)

    if txt == "🔤 Параметры опроса":
        kb = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        kb.add(KeyboardButton("🔤 Название"))
        kb.add(KeyboardButton("👥 Аудитория"))
        kb.add(KeyboardButton("🏷 Группа"))
        kb.add(BACK)

        await PollEditorStates.choosing_field.set()
        return await message.answer("Что правим в параметрах?", reply_markup=kb)

    elif txt == "📝 Вопросы":
        data = await state.get_data()
        poll_id = data["edit_poll_id"]
        # вызываем внутреннюю функцию _ask_choose_question, передаём poll_id
        return await _ask_choose_question(message, state, poll_id)

    # ❌ Готово
    await state.finish()
    return await return_to_main_menu(message)


# ——— Парам–1: поле «Название» —————————————————————————
async def process_field_choice(message: types.Message, state: FSMContext):
    txt = message.text.strip()
    if txt == BACK:
        return await _return_to_mode_menu(message, state)

    if txt == "🔤 Название":
        await PollEditorStates.editing_title.set()
        return await message.answer("Введите новый заголовок:", reply_markup=ReplyKeyboardRemove())

    if txt == "👥 Аудитория":
        kb = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        kb.add(KeyboardButton("студенты"), KeyboardButton("учителя"), KeyboardButton("все"))
        kb.add(BACK)

        await PollEditorStates.editing_target.set()
        return await message.answer("Выберите новую аудиторию:", reply_markup=kb)

    if txt == "🏷 Группа":
        async with AsyncSessionLocal() as s:
            groups = (await s.execute(select(Group))).scalars().all()
        if not groups:
            return await message.answer("Сначала создайте группы.", reply_markup=BACK_BTN)

        kb = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        for g in groups:
            kb.add(KeyboardButton(g.name))
        kb.add(KeyboardButton("❌ Без группы"))
        kb.add(BACK)

        await PollEditorStates.editing_group.set()
        return await message.answer("Выберите группу:", reply_markup=kb)

    # отмена
    return await _return_to_mode_menu(message, state)


async def process_edit_title(message: types.Message, state: FSMContext):
    txt = message.text.strip()
    if txt == BACK:
        return await _return_to_mode_menu(message, state)

    data = await state.get_data()
    poll_id = data["edit_poll_id"]
    async with AsyncSessionLocal() as s:
        await s.execute(
            Poll.__table__.update()
            .where(Poll.id == poll_id)
            .values(title=txt)
        )
        await s.commit()

    await message.answer("✅ Заголовок обновлён.", reply_markup=ReplyKeyboardRemove())
    return await _return_to_mode_menu(message, state)


async def process_edit_target(message: types.Message, state: FSMContext):
    txt = message.text.strip().lower()
    if txt == BACK.lower():
        return await _return_to_mode_menu(message, state)

    mapping = {"студенты": "student", "учителя": "teacher", "все": "all"}
    if txt not in mapping:
        return await message.answer("Пожалуйста, выберите кнопками.", reply_markup=BACK_BTN)

    data = await state.get_data()
    poll_id = data["edit_poll_id"]
    async with AsyncSessionLocal() as s:
        await s.execute(
            Poll.__table__.update()
            .where(Poll.id == poll_id)
            .values(target_role=mapping[txt])
        )
        await s.commit()

    await message.answer("✅ Аудитория обновлена.", reply_markup=ReplyKeyboardRemove())
    return await _return_to_mode_menu(message, state)


async def process_edit_group(message: types.Message, state: FSMContext):
    txt = message.text.strip()
    if txt == BACK:
        return await _return_to_mode_menu(message, state)

    data = await state.get_data()
    poll_id = data["edit_poll_id"]
    async with AsyncSessionLocal() as s:
        if txt == "❌ Без группы":
            gid = None
        else:
            grp = (await s.execute(select(Group).where(Group.name == txt))).scalar_one_or_none()
            if not grp:
                return await message.answer("Нажмите кнопку с названием группы.", reply_markup=BACK_BTN)
            gid = grp.id
        await s.execute(
            Poll.__table__.update()
            .where(Poll.id == poll_id)
            .values(group_id=gid)
        )
        await s.commit()

    await message.answer("✅ Группа обновлена.", reply_markup=ReplyKeyboardRemove())
    return await _return_to_mode_menu(message, state)


# ——— Шаг Вопросы: выбор вопроса —————————————————————————
async def _ask_choose_question(message: types.Message, state: FSMContext, poll_id: int):
    async with AsyncSessionLocal() as s:
        qs = (await s.execute(select(Question).where(Question.poll_id == poll_id))).scalars().all()
    if not qs:
        await message.answer("У опроса нет вопросов.", reply_markup=BACK_BTN)
        return await _return_to_mode_menu(message, state)

    kb = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    for i, q in enumerate(qs, 1):
        kb.add(KeyboardButton(f"{i}. {q.question_text}"))
    kb.add(BACK)

    await state.update_data(question_ids=[q.id for q in qs])
    await PollEditorStates.choosing_question.set()
    await message.answer("📝 Выберите вопрос:", reply_markup=kb)


async def choose_question(message: types.Message, state: FSMContext):
    txt = message.text.strip()
    if txt == BACK:
        return await _return_to_mode_menu(message, state)

    data = await state.get_data()
    q_ids = data.get("question_ids", [])
    idx_part = txt.split(".", 1)[0]
    if not idx_part.isdigit():
        return await message.answer("Пожалуйста, выберите вопрос кнопкой.", reply_markup=BACK_BTN)
    idx = int(idx_part) - 1
    if idx < 0 or idx >= len(q_ids):
        return await message.answer("Неверный номер.", reply_markup=BACK_BTN)

    await state.update_data(edit_q_id=q_ids[idx])

    kb = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    kb.add(KeyboardButton("🔤 Изменить текст"))
    kb.add(KeyboardButton("➕ Добавить вариант"))
    kb.add(KeyboardButton("✂️ Удалить вариант"))
    kb.add(KeyboardButton("❌ Готово"))
    kb.add(BACK)

    await PollEditorStates.action_menu.set()
    await message.answer("Выберите действие с вопросом:", reply_markup=kb)


# ——— Шаг 7: меню действий над вопросом ———————————————————
async def action_menu_handler(message: types.Message, state: FSMContext):
    txt = message.text.strip()
    if txt == BACK:
        return await _return_to_mode_menu(message, state)

    if txt == "🔤 Изменить текст":
        await PollEditorStates.editing_q_text.set()
        return await message.answer("Введите новый текст вопроса:", reply_markup=ReplyKeyboardRemove())

    if txt == "➕ Добавить вариант":
        await PollEditorStates.adding_option.set()
        return await message.answer("Отправьте текст нового варианта:", reply_markup=ReplyKeyboardRemove())

    if txt == "✂️ Удалить вариант":
        data = await state.get_data()
        q_id = data["edit_q_id"]
        async with AsyncSessionLocal() as s:
            opts = (await s.execute(select(Answer).where(Answer.question_id == q_id))).scalars().all()
        if not opts:
            return await message.answer("У этого вопроса нет вариантов.", reply_markup=BACK_BTN)

        kb = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        for i, opt in enumerate(opts, 1):
            kb.add(KeyboardButton(f"{i}. {opt.answer_text}"))
        kb.add(BACK)

        await PollEditorStates.choosing_opt_to_del.set()
        return await message.answer("Выберите вариант для удаления:", reply_markup=kb)

    # ❌ Готово → возвращаемся к режиму редактирования опроса
    return await _return_to_mode_menu(message, state)


# ——— Шаг 8а: сохраняем новый текст вопроса —————————————————
async def process_editing_q_text(message: types.Message, state: FSMContext):
    txt = message.text.strip()
    if txt == BACK:
        return await _return_to_mode_menu(message, state)

    data = await state.get_data()
    q_id = data["edit_q_id"]
    async with AsyncSessionLocal() as s:
        await s.execute(
            Question.__table__.update()
            .where(Question.id == q_id)
            .values(question_text=txt)
        )
        await s.commit()

    await message.answer("✅ Текст вопроса обновлён.", reply_markup=ReplyKeyboardRemove())
    return await _return_to_actions(message, state)


# ——— Шаг 8б: добавляем вариант —————————————————————————
async def process_adding_option(message: types.Message, state: FSMContext):
    txt = message.text.strip()
    if txt == BACK:
        return await _return_to_actions(message, state)

    data = await state.get_data()
    q_id = data["edit_q_id"]
    async with AsyncSessionLocal() as s:
        s.add(Answer(question_id=q_id, answer_text=txt))
        await s.commit()

    await message.answer(f"✅ Вариант «{txt}» добавлен.", reply_markup=ReplyKeyboardRemove())
    return await _return_to_actions(message, state)


# ——— Шаг 8в: подтверждаем удаление варианта —————————————————
async def choose_option_to_delete(message: types.Message, state: FSMContext):
    txt = message.text.strip()
    if txt == BACK:
        return await _return_to_actions(message, state)

    data = await state.get_data()
    q_id = data["edit_q_id"]
    idx_part = txt.split(".", 1)[0]
    if not idx_part.isdigit():
        return await message.answer("Пожалуйста, выберите вариант кнопкой.", reply_markup=BACK_BTN)
    idx = int(idx_part) - 1

    async with AsyncSessionLocal() as s:
        opts = (await s.execute(select(Answer).where(Answer.question_id == q_id))).scalars().all()
    if idx < 0 or idx >= len(opts):
        return await message.answer("Неверный выбор.", reply_markup=BACK_BTN)

    await state.update_data(del_opt_id=opts[idx].id)
    kb = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    kb.add(KeyboardButton("✅ Да"), KeyboardButton("❌ Нет"))
    kb.add(BACK)

    await PollEditorStates.confirming_opt_delete.set()
    await message.answer(f"Удалить вариант «{opts[idx].answer_text}»?", reply_markup=kb)


async def confirm_option_delete(message: types.Message, state: FSMContext):
    txt = message.text.strip()
    if txt == BACK:
        return await _return_to_actions(message, state)

    data = await state.get_data()
    opt_id = data["del_opt_id"]
    if txt == "✅ Да":
        async with AsyncSessionLocal() as s:
            await s.execute(delete(Answer).where(Answer.id == opt_id))
            await s.commit()
        await message.answer("✅ Вариант удалён.", reply_markup=ReplyKeyboardRemove())
    else:
        await message.answer("❌ Удаление отменено.", reply_markup=ReplyKeyboardRemove())

    return await _return_to_actions(message, state)


# ——— Вспомогательные —————————————————————————————————————
async def _return_to_mode_menu(message: types.Message, state: FSMContext):
    kb = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    kb.add(KeyboardButton("🔤 Параметры опроса"))
    kb.add(KeyboardButton("📝 Вопросы"))
    kb.add(KeyboardButton("❌ Готово"))
    kb.add(BACK)
    await PollEditorStates.choosing_mode.set()
    return await message.answer("Что правим дальше?", reply_markup=kb)

async def _return_to_actions(message: types.Message, state: FSMContext):
    kb = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    kb.add(KeyboardButton("🔤 Изменить текст"))
    kb.add(KeyboardButton("➕ Добавить вариант"))
    kb.add(KeyboardButton("✂️ Удалить вариант"))
    kb.add(KeyboardButton("❌ Готово"))
    kb.add(BACK)
    await PollEditorStates.action_menu.set()
    return await message.answer("Выберите действие с вопросом:", reply_markup=kb)


def register_poll_editor(dp: Dispatcher):
    dp.register_message_handler(start_poll_editor, text="✏️ Редактировать опрос", state="*")
    dp.register_message_handler(choose_poll, state=PollEditorStates.choosing_poll)
    dp.register_message_handler(choose_mode, state=PollEditorStates.choosing_mode)

    dp.register_message_handler(process_field_choice, state=PollEditorStates.choosing_field)
    dp.register_message_handler(process_edit_title,   state=PollEditorStates.editing_title)
    dp.register_message_handler(process_edit_target,  state=PollEditorStates.editing_target)
    dp.register_message_handler(process_edit_group,   state=PollEditorStates.editing_group)

    dp.register_message_handler(choose_question,    state=PollEditorStates.choosing_question)
    dp.register_message_handler(action_menu_handler,       state=PollEditorStates.action_menu)
    dp.register_message_handler(process_editing_q_text,   state=PollEditorStates.editing_q_text)
    dp.register_message_handler(process_adding_option,    state=PollEditorStates.adding_option)
    dp.register_message_handler(choose_option_to_delete,  state=PollEditorStates.choosing_opt_to_del)
    dp.register_message_handler(confirm_option_delete,    state=PollEditorStates.confirming_opt_delete)
