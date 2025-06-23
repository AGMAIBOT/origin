# handlers/characters_handler.py (ПОЛНАЯ НОВАЯ ВЕРСИЯ)

from telegram import Update
from telegram.ext import ContextTypes

from constants import *

# Импортируем наши модули с действиями и меню
from . import character_actions
from . import character_menus

# --- НОВЫЙ ПОДХОД: ДИСПЕТЧЕРСКИЕ СЛОВАРИ ---

# Словарь для точных совпадений callback'ов.
# Ключ: callback_data, Значение: функция-обработчик.
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
    "current_page_info": lambda u, c: None,  # Просто игнорируем нажатие на номер страницы
}

# Словарь для колбэков, начинающихся с определенного префикса.
# Ключ: префикс, Значение: функция-обработчик.
PREFIX_CALLBACK_ROUTES = {
    "category_": character_menus.show_standard_characters_menu,
    "select_char_": character_actions.handle_select_character,
    "select_custom_char_": character_actions.handle_select_character,
    "select_to_edit_": character_actions.handle_select_to_edit,
    "edit_name_": character_actions.handle_edit_name,
    "edit_prompt_": character_actions.handle_edit_prompt,
    "cancel_edit_action_": character_actions.handle_cancel_edit,
    "save_char_": character_actions.save_character_changes,
    "delete_select_": character_menus.select_char_to_delete,
    "delete_confirm_": character_actions.confirm_delete_char,
}

# --- НОВЫЙ ГЛАВНЫЙ РОУТЕР КОЛБЭКОВ ---

async def handle_character_callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """
    Обрабатывает ВСЕ callback'и, связанные с персонажами, используя диспетчерские словари.
    Возвращает True, если callback был обработан, иначе False.
    """
    query = update.callback_query
    if not query: return False
    
    callback_data = query.data
    
    # 1. Проверяем точные совпадения
    if callback_data in EXACT_CALLBACK_ROUTES:
        await query.answer()
        await EXACT_CALLBACK_ROUTES[callback_data](update, context)
        return True

    # 2. Проверяем совпадения по префиксу
    for prefix, handler in PREFIX_CALLBACK_ROUTES.items():
        if callback_data.startswith(prefix):
            await query.answer()
            # Передаем prefix в обработчик, чтобы он мог извлечь ID или другие данные
            await handler(update, context, prefix=prefix)
            return True
            
    # 3. Отдельно обрабатываем пагинацию, т.к. ее логика чуть сложнее
    page_callbacks = {
        "next_char_page": (CURRENT_CHAR_VIEW_PAGE_KEY, 1, character_menus.show_standard_characters_menu),
        "prev_char_page": (CURRENT_CHAR_VIEW_PAGE_KEY, -1, character_menus.show_standard_characters_menu),
        "next_custom_char_page": (CURRENT_CHAR_VIEW_PAGE_KEY, 1, character_menus.show_paginated_custom_characters_menu),
        "prev_custom_char_page": (CURRENT_CHAR_VIEW_PAGE_KEY, -1, character_menus.show_paginated_custom_characters_menu),
        "next_manage_page": (CURRENT_CHAR_MANAGE_PAGE_KEY, 1, None), # Handler определяется по режиму
        "prev_manage_page": (CURRENT_CHAR_MANAGE_PAGE_KEY, -1, None),
    }

    if callback_data in page_callbacks:
        await query.answer()
        page_key, delta, handler = page_callbacks[callback_data]
        context.user_data[page_key] = context.user_data.get(page_key, 0) + delta
        
        if handler:
            await handler(update, context)
        else: # Специальная логика для пагинации в меню "Управление"
            mode = context.user_data.get(MANAGE_MODE_KEY)
            if mode == 'edit': await character_menus.edit_custom_char_start(update, context)
            elif mode == 'delete': await character_menus.delete_custom_char_start(update, context)
        return True

    # Если ни один маршрут не подошел, возвращаем False
    return False


async def handle_stateful_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """
    Обрабатывает сообщения от пользователя, когда бот находится в определенном состоянии.
    (Этот код остается без изменений, но теперь он более изолирован от логики колбэков).
    """
    current_state = context.user_data.get('state', STATE_NONE)
    if current_state == STATE_NONE:
        return False

    # Словарь состояний
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