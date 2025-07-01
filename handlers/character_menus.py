# handlers/character_menus.py (РЕФАКТОРИНГ НА HTML)

import html
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Message
from telegram.error import BadRequest
from telegram.ext import ContextTypes
from io import BytesIO
import database as db
import config
from characters import DEFAULT_CHARACTER_NAME, CHARACTER_CATEGORIES, ALL_PROMPTS
from constants import *
from utils import get_actual_user_tier

TIER_HIERARCHY = {TIER_FREE: 0, TIER_LITE: 1, TIER_PRO: 2}

# [Dev-Ассистент]: ОБНОВЛЕННЫЕ СЛОВАРИ ДЛЯ НОВОЙ КАТЕГОРИИ "AGM Учителя"
CATEGORY_DESCRIPTIONS = {
    "conversational": "А иногда ведь просто хочется поболтать по душам, без всяких там задач и серьезных решений, правда? Здесь тебя ждут персонажи, которые умеют слушать, слышать между строк и даже делиться своим настроением. Забудь про сухие факты – это те, кто готов просто быть рядом и разделить с тобой момент.\n",
    "specialists": "Нужен дельный совет или помощь в сложной ситуации? В этом разделе собрались настоящие мастера своего дела! От технического гуру до знатока растений – каждый из них готов поделиться глубокими знаниями, дать практичные советы и помочь разобраться в любом вопросе. Они здесь, чтобы решать твои проблемы, а не просто слушать!",
    "quest": "Надоело просто читать? Здесь ты – главный герой! Погружайся в захватывающие интерактивные миры, где каждый твой выбор реально меняет сюжет и ведет к одной из уникальных концовок. От пиратских приключений до борьбы за выживание — готовься, скучно точно не будет!",
    "teachers": "🎓 В этом разделе тебя ждут мудрые наставники, готовые помочь освоить новые знания и навыки. От математики до программирования, от истории до искусства — здесь каждый найдет своего идеального преподавателя, способного объяснить сложные концепции простым языком и провести тебя через процесс обучения с удовольствием." # <<< [Dev-Ассистент]: НОВАЯ КАТЕГОРИЯ
}
CATEGORY_DISPLAY_NAMES = {
    "conversational": "Разговорные",
    "specialists": "Специалисты",
    "quest": "Ролевые игры (Quest)",
    "teachers": "🎓 AGM Учителя" # <<< [Dev-Ассистент]: НОВАЯ КАТЕГОРИЯ
}
raw_text = "Добро пожаловать в уголок, где алгоритмы обретают... ну, почти душу! В разделе 'Персонажи' ты найдешь не просто наборы кода, а настоящих экспертов, готовых разрулить любую твою проблему; душевных собеседников, которые всегда поддержат разговор; и, конечно, харизматичных Мастеров квестов, что затянут тебя в эпические приключения. Выбери того, кто тебе по вкусу – и пусть начнется магия общения (или выживания)!"


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
    
    user_tier_name = await get_actual_user_tier(user)
    user_tier_level = TIER_HIERARCHY.get(user_tier_name, 0)

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
                char_info = ALL_PROMPTS.get(char_name, {})
                
                prefix = ""
                required_tier_name = char_info.get('required_tier', TIER_FREE)
                required_tier_level = TIER_HIERARCHY.get(required_tier_name, 0)
                
                if user_tier_level < required_tier_level:
                    prefix = "🔒 "
                elif char_name == current_char_name:
                    prefix = "✅ "
                
                display_name = f"{prefix}{html.escape(char_name)}"
                row.append(InlineKeyboardButton(display_name, callback_data=f"show_char_{char_name}"))
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
    
    action_prefixes = {'view': ("show_custom_char_", ""), 'edit': ("select_to_edit_", "🔧 "), 'delete': ("delete_select_", "🗑️ ")}
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
                display_name = f"{icon}{html.escape(char['name'])}"
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
    text = f"{html.escape(raw_text)}"
    keyboard = [
        [InlineKeyboardButton("🗣️ Разговорные", callback_data="category_conversational")],
        [InlineKeyboardButton("🎓 Специалисты", callback_data="category_specialists")],
        [InlineKeyboardButton("🎓 AGM Учителя", callback_data="category_teachers")],
        [InlineKeyboardButton("⚔️ Ролевые игры (Quest)", callback_data="category_quest")],
        [InlineKeyboardButton("🎭 Мои Персонажи", callback_data="my_custom_characters_hub")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    if update.callback_query: await update.callback_query.edit_message_text(text, reply_markup=reply_markup, parse_mode='HTML')
    else: await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='HTML')

async def show_standard_characters_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, **kwargs) -> None:
    query = update.callback_query
    if query.data.startswith("category_"):
        category_name = query.data.replace("category_", "")
        context.user_data[CURRENT_CHAR_CATEGORY_KEY] = category_name
        context.user_data[CURRENT_CHAR_VIEW_PAGE_KEY] = 0
    
    user_id = await get_user_id(update)
    reply_markup = await _build_standard_character_keyboard(user_id, context)
    
    category_name = context.user_data.get(CURRENT_CHAR_CATEGORY_KEY, "conversational")
    category_description = CATEGORY_DESCRIPTIONS.get(category_name, "Выберите персонажа из этой категории:")
    display_category_name = CATEGORY_DISPLAY_NAMES.get(category_name, category_name.capitalize())

    text = (
        f"Категория: <b>{html.escape(display_category_name)}</b>\n"
        f"{html.escape(category_description)}\n"
        f"Выберите персонажа:"
    )
    
    try: 
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='HTML')
    except BadRequest as e:
        if "Message is not modified" in str(e): 
            await query.answer()
        else: 
            raise
        
async def show_my_characters_hub_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = "🎭 <b>Мои Персонажи</b>"
    keyboard = [[InlineKeyboardButton("📖 Просмотр и выбор", callback_data="view_my_chars")],[InlineKeyboardButton("⚙️ Управление (создать, изменить, удалить)", callback_data="manage_custom_characters")],[InlineKeyboardButton("⬅️ Назад к категориям", callback_data="back_to_categories")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    if update.callback_query: await update.callback_query.edit_message_text(text, reply_markup=reply_markup, parse_mode='HTML')

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
    text = "<b>Ваши персонажи:</b>\n\nВыберите персонажа для общения:"
    try:
        if is_new_message: await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='HTML')
        else: await update.callback_query.edit_message_text(text, reply_markup=reply_markup, parse_mode='HTML')
    except BadRequest as e:
        if "Message is not modified" in str(e): await update.callback_query.answer()
        else: raise

async def show_manage_characters_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    clear_temp_state(context)
    text = "👾 <b>Управление персонажами</b>"
    keyboard = [[InlineKeyboardButton("➕ Добавить", callback_data="add_custom_char_start")],[InlineKeyboardButton("🔧 Изменить", callback_data="edit_custom_char_start")],[InlineKeyboardButton("🗑️ Удалить", callback_data="delete_custom_char_start")],[InlineKeyboardButton("⬅️ Назад", callback_data="my_custom_characters_hub")]]
    if update.callback_query: await update.callback_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')

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
        
    text = f"⚙️ Редактирование: <b>{html.escape(char_name)}</b>"
    keyboard = [
        [InlineKeyboardButton("✏️ Изменить Имя", callback_data=f"edit_name_{char_id}")],
        [InlineKeyboardButton("📜 Изменить Промпт", callback_data=f"edit_prompt_{char_id}")],
        [InlineKeyboardButton("💾 Сохранить", callback_data=f"save_char_{char_id}")],
        [InlineKeyboardButton("⬅️ Назад", callback_data="back_to_manage_chars")]
    ]
    try:
        await message_to_edit.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')
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

    char_id = context.user_data.get(TEMP_CHAR_ID)
    keyboard = [
        [InlineKeyboardButton("📄 Показать полный промпт в файле txt", callback_data=f"show_full_prompt_{char_id}")],
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
    keyboard = [[InlineKeyboardButton(f"✅ Да, удалить '{html.escape(char_data['name'])}'", callback_data=f"delete_confirm_{char_id}")],[InlineKeyboardButton("❌ Нет, назад", callback_data="delete_custom_char_start")]]
    await query.edit_message_text("Вы уверены?", reply_markup=InlineKeyboardMarkup(keyboard))