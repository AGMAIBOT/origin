# handlers/character_menus.py (ИСПРАВЛЕННАЯ ВЕРСИЯ)

import html
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Message
from telegram.error import BadRequest
from telegram.ext import ContextTypes
from telegram.helpers import escape_markdown
from io import BytesIO
import database as db
import config  # <<< Импортируем config
from characters import DEFAULT_CHARACTER_NAME, CHARACTER_CATEGORIES
from constants import * # <<< Импортируем константы

# ... остальная часть файла character_menus.py остается без изменений ...
def clear_temp_state(context: ContextTypes.DEFAULT_TYPE):
    context.user_data['state'] = STATE_NONE
    context.user_data.pop(TEMP_CHAR_ID, None)
    context.user_data.pop(TEMP_CHAR_NAME, None)
    context.user_data.pop(TEMP_CHAR_PROMPT, None)
async def get_user_id(update: Update) -> int:
    return await db.add_or_update_user(update.effective_user.id, update.effective_user.full_name, update.effective_user.username)
async def _build_standard_character_keyboard(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> InlineKeyboardMarkup:
    user = await db.get_user_by_id(user_id)
    current_char_name = user['current_character_name'] if user else DEFAULT_CHARACTER_NAME
    current_category = context.user_data.get(CURRENT_CHAR_CATEGORY_KEY, "conversational")
    all_character_names = sorted(CHARACTER_CATEGORIES.get(current_category, []))
    current_page = context.user_data.get(CURRENT_CHAR_VIEW_PAGE_KEY, 0)
    total_pages = (len(all_character_names) + config.CHARACTERS_PER_PAGE - 1) // config.CHARACTERS_PER_PAGE
    start_index = current_page * config.CHARACTERS_PER_PAGE
    end_index = start_index + config.CHARACTERS_PER_PAGE
    characters_on_page = all_character_names[start_index:end_index]
    keyboard = []
    for i in range(0, len(characters_on_page), 2):
        row = []
        for j in range(2):
            if i + j < len(characters_on_page):
                char_name = characters_on_page[i+j]
                display_name = f"✅ {escape_markdown(char_name, version=2)}" if char_name == current_char_name else escape_markdown(char_name, version=2)
                row.append(InlineKeyboardButton(display_name, callback_data=f"select_char_{char_name}"))
        keyboard.append(row)
    pagination_row = []
    if current_page > 0: pagination_row.append(InlineKeyboardButton("⬅️", callback_data="prev_char_page"))
    if total_pages > 1: pagination_row.append(InlineKeyboardButton(f"{current_page + 1}/{total_pages}", callback_data="current_page_info"))
    if current_page < total_pages - 1: pagination_row.append(InlineKeyboardButton("➡️", callback_data="next_char_page"))
    if pagination_row: keyboard.append(pagination_row)
    keyboard.append([InlineKeyboardButton("⬅️ Назад к категориям", callback_data="back_to_categories")])
    return InlineKeyboardMarkup(keyboard)
async def _build_paginated_custom_char_keyboard(user_id: int, custom_chars: list, context: ContextTypes.DEFAULT_TYPE, mode: str) -> InlineKeyboardMarkup:
    page_key = CURRENT_CHAR_VIEW_PAGE_KEY if mode == 'view' else CURRENT_CHAR_MANAGE_PAGE_KEY
    current_page = context.user_data.get(page_key, 0)
    total_pages = (len(custom_chars) + config.CHARACTERS_PER_PAGE - 1) // config.CHARACTERS_PER_PAGE
    start_index = current_page * config.CHARACTERS_PER_PAGE
    end_index = start_index + config.CHARACTERS_PER_PAGE
    characters_on_page = custom_chars[start_index:end_index]
    action_prefixes = {'view': ("select_custom_char_", ""), 'edit': ("select_to_edit_", "🔧 "), 'delete': ("delete_select_", "🗑️ ")}
    callback_prefix, icon = action_prefixes[mode]
    keyboard = []
    current_char_name = ""
    if mode == 'view':
        user = await db.get_user_by_id(user_id)
        current_char_name = user.get('current_character_name', DEFAULT_CHARACTER_NAME)
    for i in range(0, len(characters_on_page), 2):
        row = []
        for j in range(2):
            if i + j < len(characters_on_page):
                char = characters_on_page[i+j]
                display_name = f"{icon}{escape_markdown(char['name'], version=2)}"
                if mode == 'view' and char['name'] == current_char_name: display_name = f"✅ {display_name}"
                row.append(InlineKeyboardButton(display_name, callback_data=f"{callback_prefix}{char['id']}"))
        keyboard.append(row)
    page_callback_prefixes = {
        'view': ("prev_custom_char_page", "next_custom_char_page"),
        'edit': ("prev_manage_page", "next_manage_page"),
        'delete': ("prev_manage_page", "next_manage_page")
    }
    prev_page_cb, next_page_cb = page_callback_prefixes[mode]
    pagination_row = []
    if current_page > 0: pagination_row.append(InlineKeyboardButton("⬅️", callback_data=prev_page_cb))
    if total_pages > 1: pagination_row.append(InlineKeyboardButton(f"{current_page + 1}/{total_pages}", callback_data="current_page_info"))
    if current_page < total_pages - 1: pagination_row.append(InlineKeyboardButton("➡️", callback_data=next_page_cb))
    if pagination_row: keyboard.append(pagination_row)
    back_callbacks = {'view': "my_custom_characters_hub", 'edit': "back_to_manage_chars", 'delete': "back_to_manage_chars"}
    keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data=back_callbacks[mode])])
    return InlineKeyboardMarkup(keyboard)
async def show_character_categories_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = "Выберите категорию персонажей:"
    keyboard = [[InlineKeyboardButton("🗣️ Разговорные", callback_data="category_conversational")],
                [InlineKeyboardButton("🎓 Специалисты", callback_data="category_specialists")],
                [InlineKeyboardButton("⚔️ Ролевые игры (Quest)", callback_data="category_quest")],
                [InlineKeyboardButton("🎭 Мои Персонажи", callback_data="my_custom_characters_hub")],]
    reply_markup = InlineKeyboardMarkup(keyboard)
    if update.callback_query: await update.callback_query.edit_message_text(text, reply_markup=reply_markup)
    else: await update.message.reply_text(text, reply_markup=reply_markup)
async def show_standard_characters_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, **kwargs) -> None:
    query = update.callback_query
    if query.data.startswith("category_"):
        category_name = query.data.replace("category_", "")
        context.user_data[CURRENT_CHAR_CATEGORY_KEY] = category_name
        context.user_data[CURRENT_CHAR_VIEW_PAGE_KEY] = 0
    user_id = await get_user_id(update)
    reply_markup = await _build_standard_character_keyboard(user_id, context)
    category_name = context.user_data.get(CURRENT_CHAR_CATEGORY_KEY, "conversational")
    text = f"Категория: *{escape_markdown(category_name.capitalize(), version=2)}*\n\nВыберите персонажа:"
    try: await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='MarkdownV2')
    except BadRequest as e:
        if "Message is not modified" in str(e): await query.answer()
        else: raise
async def show_my_characters_hub_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = "🎭 *Мои Персонажи*"
    keyboard = [[InlineKeyboardButton("📖 Просмотр и выбор", callback_data="view_my_chars")],[InlineKeyboardButton("⚙️ Управление (создать, изменить, удалить)", callback_data="manage_custom_characters")],[InlineKeyboardButton("⬅️ Назад к категориям", callback_data="back_to_categories")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    if update.callback_query: await update.callback_query.edit_message_text(text, reply_markup=reply_markup, parse_mode='MarkdownV2')
async def show_paginated_custom_characters_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, is_new_message: bool = False) -> None:
    context.user_data.setdefault(CURRENT_CHAR_VIEW_PAGE_KEY, 0)
    user_id = await get_user_id(update)
    custom_chars = await db.get_user_characters(user_id)
    if not custom_chars:
        text = "У вас пока нет созданных персонажей."
        keyboard = [[InlineKeyboardButton("➕ Создать первого персонажа", callback_data="add_custom_char_start_from_empty")],[InlineKeyboardButton("⬅️ Назад", callback_data="my_custom_characters_hub")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        if is_new_message: await update.message.reply_text(text, reply_markup=reply_markup)
        else: await update.callback_query.edit_message_text(text, reply_markup=reply_markup)
        return
    reply_markup = await _build_paginated_custom_char_keyboard(user_id, custom_chars, context, mode='view')
    text = "*Ваши персонажи:*\n\nВыберите персонажа для общения:"
    try:
        if is_new_message: await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='MarkdownV2')
        else: await update.callback_query.edit_message_text(text, reply_markup=reply_markup, parse_mode='MarkdownV2')
    except BadRequest as e:
        if "Message is not modified" in str(e): await update.callback_query.answer()
        else: raise
async def show_manage_characters_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    clear_temp_state(context)
    text = "👾 *Управление персонажами*"
    keyboard = [[InlineKeyboardButton("➕ Добавить", callback_data="add_custom_char_start")],[InlineKeyboardButton("🔧 Изменить", callback_data="edit_custom_char_start")],[InlineKeyboardButton("🗑️ Удалить", callback_data="delete_custom_char_start")],[InlineKeyboardButton("⬅️ Назад", callback_data="my_custom_characters_hub")]]
    if update.callback_query: await update.callback_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='MarkdownV2')
async def add_custom_char_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data['original_update_for_creation'] = update
    context.user_data['state'] = STATE_WAITING_FOR_NEW_CHAR_NAME
    keyboard = [[InlineKeyboardButton("❌ Отмена", callback_data="cancel_creation_action")]]
    await update.callback_query.edit_message_text("Введите имя для нового персонажа:", reply_markup=InlineKeyboardMarkup(keyboard))
async def edit_custom_char_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    context.user_data[MANAGE_MODE_KEY] = 'edit'
    context.user_data.setdefault(CURRENT_CHAR_MANAGE_PAGE_KEY, 0)
    user_id = await get_user_id(update)
    custom_chars = await db.get_user_characters(user_id)
    if not custom_chars: return await query.answer("У вас нет персонажей для изменения.", show_alert=True)
    reply_markup = await _build_paginated_custom_char_keyboard(user_id, custom_chars, context, mode='edit')
    await query.edit_message_text("Выберите персонажа для изменения:", reply_markup=reply_markup)
async def delete_custom_char_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    context.user_data[MANAGE_MODE_KEY] = 'delete'
    context.user_data.setdefault(CURRENT_CHAR_MANAGE_PAGE_KEY, 0)
    user_id = await get_user_id(update)
    custom_chars = await db.get_user_characters(user_id)
    if not custom_chars: return await query.answer("У вас нет персонажей для удаления.", show_alert=True)
    reply_markup = await _build_paginated_custom_char_keyboard(user_id, custom_chars, context, mode='delete')
    await query.edit_message_text("Выберите персонажа для удаления:", reply_markup=reply_markup)
async def show_edit_character_menu(message_to_edit: Message, context: ContextTypes.DEFAULT_TYPE):
    char_id = context.user_data.get(TEMP_CHAR_ID)
    if not char_id:
        await message_to_edit.edit_text("Ошибка: не найден персонаж для редактирования. Начните сначала.", reply_markup=None)
        return
    char_name = context.user_data.get(TEMP_CHAR_NAME)
    if not char_name:
        original_char = await db.get_character_by_id(char_id)
        if not original_char:
            await message_to_edit.edit_text("Ошибка: персонаж был удален из базы данных.", reply_markup=None)
            return
        context.user_data[TEMP_CHAR_NAME] = original_char['name']
        context.user_data[TEMP_CHAR_PROMPT] = original_char['prompt']
        char_name = original_char['name']
    text = f"⚙️ Редактирование: *{escape_markdown(char_name, version=2)}*"
    keyboard = [
        [InlineKeyboardButton("✏️ Изменить Имя", callback_data=f"edit_name_{char_id}")],
        [InlineKeyboardButton("📜 Изменить Промпт", callback_data=f"edit_prompt_{char_id}")],
        [InlineKeyboardButton("💾 Сохранить", callback_data=f"save_char_{char_id}")],
        [InlineKeyboardButton("⬅️ Назад", callback_data="back_to_manage_chars")]
    ]
    try:
        await message_to_edit.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='MarkdownV2')
    except BadRequest as e:
        if "Message is not modified" in str(e):
            pass
        else:
            logging.error(f"Не удалось отредактировать сообщение для меню: {e}", exc_info=True)
            raise
async def prompt_for_new_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    context.user_data['state'] = STATE_EDITING_CHAR_NAME
    keyboard = [[InlineKeyboardButton("❌ Отмена", callback_data=f"cancel_edit_action_{context.user_data[TEMP_CHAR_ID]}")]]
    await update.callback_query.message.edit_text("Введите новое имя для персонажа:", reply_markup=InlineKeyboardMarkup(keyboard))

async def prompt_for_new_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    current_prompt = context.user_data.get(TEMP_CHAR_PROMPT, "Промпт не найден.")
    prompt_preview = (current_prompt[:1000] + '...') if len(current_prompt) > 1000 else current_prompt
    text = f"Текущий промпт:\n<pre>{html.escape(prompt_preview)}</pre>\n\nОтправьте новый промпт (текст/файл)."
    context.user_data['state'] = STATE_EDITING_CHAR_PROMPT

    # [Dev-Ассистент]: НАЧАЛО ИЗМЕНЕНИЙ
    # [Dev-Ассистент]: Собираем новую клавиатуру с двумя кнопками.
    char_id = context.user_data.get(TEMP_CHAR_ID)
    keyboard = [
        # [Dev-Ассистент]: Новая кнопка, которая будет запрашивать файл.
        [InlineKeyboardButton("📄 Показать полный промпт в файле txt", callback_data=f"show_full_prompt_{char_id}")],
        # [Dev-Ассистент]: Старая кнопка отмены.
        [InlineKeyboardButton("❌ Отмена", callback_data=f"cancel_edit_action_{char_id}")]
    ]
    await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')

async def select_char_to_delete(update: Update, context: ContextTypes.DEFAULT_TYPE, **kwargs) -> None:
    query = update.callback_query
    char_id = int(query.data.replace("delete_select_", ""))
    char_data = await db.get_character_by_id(char_id)
    if not char_data:
        await query.answer("Персонаж не найден.", show_alert=True)
        return
    keyboard = [[InlineKeyboardButton(f"✅ Да, удалить '{char_data['name']}'", callback_data=f"delete_confirm_{char_id}")],[InlineKeyboardButton("❌ Нет, назад", callback_data="delete_custom_char_start")]]
    await query.edit_message_text("Вы уверены?", reply_markup=InlineKeyboardMarkup(keyboard))