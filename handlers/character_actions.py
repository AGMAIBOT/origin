# handlers/character_actions.py (ИСПРАВЛЕННАЯ ВЕРСИЯ)

import html
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes
from telegram.error import BadRequest
from telegram.helpers import escape_markdown

from characters import DEFAULT_CHARACTER_NAME, ALL_PROMPTS
import database as db
import config  # <<< Импортируем config
from constants import * # <<< Здесь остаются все константы
from utils import delete_message_callback, get_text_content_from_document
from . import character_menus

class FileSizeError(Exception): pass
    
# ... остальная часть файла character_actions.py остается без изменений ...
async def get_user_id(update: Update) -> int:
    return await db.add_or_update_user(update.effective_user.id, update.effective_user.full_name, update.effective_user.username)
async def handle_new_char_name_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    char_name = update.message.text.strip()
    user_id = await get_user_id(update)
    if char_name in ALL_PROMPTS:
        await update.message.reply_text(f"Имя '{char_name}' зарезервировано. Выберите другое.")
        return
    if await db.get_custom_character_by_name(user_id, char_name):
        await update.message.reply_text(f"У вас уже есть персонаж '{char_name}'. Выберите другое имя.")
        return
    context.user_data[TEMP_CHAR_NAME] = char_name
    context.user_data['state'] = STATE_WAITING_FOR_NEW_CHAR_PROMPT
    await update.message.reply_text(f"Имя '{char_name}' принято. Теперь введите промпт (текстом или .txt файлом):")
async def handle_new_char_prompt_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    char_name = context.user_data.get(TEMP_CHAR_NAME)
    try:
        prompt = await get_text_content_from_document(update.message.document, context) if update.message.document else update.message.text.strip()
    except (ValueError, FileSizeError) as e:
        return await update.message.reply_text(f"Ошибка: {e}")
    if not char_name or not prompt:
        await update.message.reply_text("Ошибка: имя или промпт пусты.")
        character_menus.clear_temp_state(context)
        return
    user_id = await get_user_id(update)
    await db.add_character(user_id, char_name, prompt)
    prompt_preview = (prompt[:1000] + '...') if len(prompt) > 1000 else prompt
    await update.message.reply_html(f"✅ Персонаж <b>{html.escape(char_name)}</b> успешно создан!\n\n<b>Промпт:</b>\n<pre>{html.escape(prompt_preview)}</pre>")
    character_menus.clear_temp_state(context)
    context.user_data[CURRENT_CHAR_VIEW_PAGE_KEY] = 0
    await character_menus.show_paginated_custom_characters_menu(update, context, is_new_message=True)
async def handle_edited_name_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    new_name = update.message.text.strip()
    context.user_data[TEMP_CHAR_NAME] = new_name
    context.user_data['state'] = STATE_NONE
    await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=update.message.message_id)
    await character_menus.show_edit_character_menu(context.user_data.pop('last_callback_query').message, context)
async def handle_edited_prompt_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        prompt_text = await get_text_content_from_document(update.message.document, context) if update.message.document else update.message.text.strip()
        context.user_data[TEMP_CHAR_PROMPT] = prompt_text
        context.user_data['state'] = STATE_NONE
        await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=update.message.message_id)
        await character_menus.show_edit_character_menu(context.user_data.pop('last_callback_query').message, context)
    except (ValueError, FileSizeError) as e:
        await update.message.reply_text(f"Ошибка: {e}\n\nПожалуйста, отправьте корректный файл или текст.", quote=True)
async def save_character_changes(update: Update, context: ContextTypes.DEFAULT_TYPE, **kwargs) -> None:
    query = update.callback_query
    char_id = context.user_data.get(TEMP_CHAR_ID)
    new_name = context.user_data.get(TEMP_CHAR_NAME)
    new_prompt = context.user_data.get(TEMP_CHAR_PROMPT)
    if not all([char_id, new_name, new_prompt]):
        await query.edit_message_text("Ошибка: нет данных для сохранения.", reply_markup=None)
        return
    user_id = await get_user_id(update)
    user_data = await db.get_user_by_id(user_id)
    original_char = await db.get_character_by_id(char_id)
    if user_data and original_char and user_data['current_character_name'] == original_char['name'] and original_char['name'] != new_name:
        await db.set_current_character(user_id, new_name)
    await db.update_character(char_id, new_name, new_prompt)
    await query.edit_message_text(f"✅ Персонаж <b>{html.escape(new_name)}</b> сохранен!", parse_mode='HTML')
    character_menus.clear_temp_state(context)
    context.job_queue.run_once(lambda ctx: character_menus.show_manage_characters_menu(update, ctx), 2)
async def handle_select_character(update: Update, context: ContextTypes.DEFAULT_TYPE, prefix: str) -> None:
    query = update.callback_query
    user_id = await get_user_id(update)
    is_custom = prefix == "select_custom_char_"
    char_name = ""
    if is_custom:
        char_id = int(query.data.replace(prefix, ""))
        char_data = await db.get_character_by_id(char_id)
        if not char_data:
            await query.answer("Персонаж не найден (возможно, удален).", show_alert=True)
            return
        char_name = char_data['name']
    else:
        char_name = query.data.replace(prefix, "")
    user_data = await db.get_user_by_id(user_id)
    if user_data and user_data['current_character_name'] == char_name:
        await query.answer(f"Персонаж '{char_name}' уже выбран.")
        return
    await db.set_current_character(user_id, char_name)
    await query.answer(f"Выбран: {char_name}")
    try:
        if is_custom:
            await character_menus.show_paginated_custom_characters_menu(update, context)
        else:
            await query.edit_message_reply_markup(reply_markup=await character_menus._build_standard_character_keyboard(user_id, context))
    except BadRequest as e:
        if "Message is not modified" not in str(e): raise
    text = f"Персонаж изменен на *{escape_markdown(char_name, version=2)}*\\."
    sent_message = await query.message.reply_text(text=text, parse_mode='MarkdownV2')
    context.job_queue.run_once(delete_message_callback, 3, data={'chat_id': sent_message.chat_id, 'message_id': sent_message.message_id})
async def handle_select_to_edit(update: Update, context: ContextTypes.DEFAULT_TYPE, prefix: str) -> None:
    char_id = int(update.callback_query.data.replace(prefix, ""))
    context.user_data[TEMP_CHAR_ID] = char_id
    context.user_data.pop(TEMP_CHAR_NAME, None)
    context.user_data.pop(TEMP_CHAR_PROMPT, None)
    await character_menus.show_edit_character_menu(update.callback_query.message, context)
async def handle_edit_name(update: Update, context: ContextTypes.DEFAULT_TYPE, prefix: str) -> None:
    context.user_data['last_callback_query'] = update.callback_query
    await character_menus.prompt_for_new_name(update, context)
async def handle_edit_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE, prefix: str) -> None:
    context.user_data['last_callback_query'] = update.callback_query
    await character_menus.prompt_for_new_prompt(update, context)
async def handle_cancel_edit(update: Update, context: ContextTypes.DEFAULT_TYPE, prefix: str) -> None:
    context.user_data['state'] = STATE_NONE
    await character_menus.show_edit_character_menu(update.callback_query.message, context)
async def confirm_delete_char(update: Update, context: ContextTypes.DEFAULT_TYPE, prefix: str) -> None:
    query = update.callback_query
    char_id = int(query.data.replace(prefix, ""))
    char_to_delete = await db.get_character_by_id(char_id)
    if not char_to_delete:
        await query.answer("Персонаж уже удален.", show_alert=True)
        return
    user_id = await get_user_id(update)
    user_data = await db.get_user_by_id(user_id)
    await db.delete_character(char_id)
    await query.answer(f"Персонаж '{char_to_delete['name']}' удален.")
    if user_data and user_data['current_character_name'] == char_to_delete['name']:
         await db.set_current_character(user_id, DEFAULT_CHARACTER_NAME)
    await character_menus.show_manage_characters_menu(update, context)