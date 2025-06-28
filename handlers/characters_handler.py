# handlers/characters_handler.py

from telegram import Update
from telegram.ext import ContextTypes

from constants import *
from . import character_actions
from . import character_menus

# --- Диспетчерские словари с новыми маршрутами ---
EXACT_CALLBACK_ROUTES = {
    "my_custom_characters_hub": character_menus.show_my_characters_hub_menu,
    "view_my_chars": character_menus.show_paginated_custom_characters_menu,
    "manage_custom_characters": character_menus.show_manage_characters_menu,
    "back_to_categories": character_menus.show_character_categories_menu,
    "back_to_manage_chars": character_menus.show_manage_characters_menu,
    "add_custom_char_start": character_menus.add_custom_char_start,
    "add_custom_char_start_from_empty": character_menus.add_custom_char_start,
    "cancel_creation_action": character_menus.show_manage_characters_menu,
    "edit_custom_char_start": character_menus.edit_custom_char_start,
    "delete_custom_char_start": character_menus.delete_custom_char_start,
    "current_page_info": lambda u, c: None,
    # [Dev-Ассистент]: НОВЫЕ МАРШРУТЫ для кнопок "Назад" с карточки персонажа.
    "back_to_standard_list": character_menus.show_standard_characters_menu,
    "back_to_custom_list": character_menus.show_paginated_custom_characters_menu,
}

PREFIX_CALLBACK_ROUTES = {
    # [Dev-Ассистент]: НОВЫЕ МАРШРУТЫ для показа карточки и подтверждения выбора.
    "show_char_": character_actions.show_character_card,
    "show_custom_char_": character_actions.show_character_card,
    "confirm_char_": character_actions.confirm_character_selection,
    "confirm_custom_char_": character_actions.confirm_character_selection,
    
    # [Dev-Ассистент]: Старые маршруты для управления персонажами.
    "show_full_prompt_": character_actions.handle_show_full_prompt,
    "category_": character_menus.show_standard_characters_menu,
    "select_to_edit_": character_actions.handle_select_to_edit,
    "edit_name_": character_actions.handle_edit_name,
    "edit_prompt_": character_actions.handle_edit_prompt,
    "cancel_edit_action_": character_actions.handle_cancel_edit,
    "save_char_": character_actions.save_character_changes,
    "delete_select_": character_menus.select_char_to_delete,
    "delete_confirm_": character_actions.confirm_delete_char,
}

# --- Главный роутер (остается почти без изменений, но теперь работает с новыми маршрутами) ---
async def handle_character_callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    query = update.callback_query
    if not query: return False
    callback_data = query.data
    
    if callback_data in EXACT_CALLBACK_ROUTES:
        # [Dev-Ассистент]: Не отвечаем здесь, чтобы не было двойного ответа.
        # await query.answer() 
        await EXACT_CALLBACK_ROUTES[callback_data](update, context)
        return True

    for prefix, handler in PREFIX_CALLBACK_ROUTES.items():
        if callback_data.startswith(prefix):
            await handler(update, context, prefix=prefix)
            return True
            
    page_callbacks = {
        "next_char_page": (CURRENT_CHAR_VIEW_PAGE_KEY, 1, character_menus.show_standard_characters_menu),
        "prev_char_page": (CURRENT_CHAR_VIEW_PAGE_KEY, -1, character_menus.show_standard_characters_menu),
        "next_custom_char_page": (CURRENT_CHAR_VIEW_PAGE_KEY, 1, character_menus.show_paginated_custom_characters_menu),
        "prev_custom_char_page": (CURRENT_CHAR_VIEW_PAGE_KEY, -1, character_menus.show_paginated_custom_characters_menu),
        "next_manage_page": (CURRENT_CHAR_MANAGE_PAGE_KEY, 1, None),
        "prev_manage_page": (CURRENT_CHAR_MANAGE_PAGE_KEY, -1, None),
    }

    if callback_data in page_callbacks:
        await query.answer()
        page_key, delta, handler = page_callbacks[callback_data]
        context.user_data[page_key] = context.user_data.get(page_key, 0) + delta
        if handler:
            await handler(update, context)
        else:
            mode = context.user_data.get(MANAGE_MODE_KEY)
            if mode == 'edit': await character_menus.edit_custom_char_start(update, context)
            elif mode == 'delete': await character_menus.delete_custom_char_start(update, context)
        return True

    return False

# --- Обработчик сообщений в состояниях (без изменений) ---
async def handle_stateful_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    # ... (код без изменений)
    current_state = context.user_data.get('state', STATE_NONE)
    if current_state == STATE_NONE:
        return False
    state_routes = {
        STATE_WAITING_FOR_NEW_CHAR_NAME: character_actions.handle_new_char_name_input,
        STATE_WAITING_FOR_NEW_CHAR_PROMPT: character_actions.handle_new_char_prompt_input,
        STATE_EDITING_CHAR_NAME: character_actions.handle_edited_name_input,
        STATE_EDITING_CHAR_PROMPT: character_actions.handle_edited_prompt_input,
    }
    handler = state_routes.get(current_state)
    if handler:
        await handler(update, context)
        return True
    return False