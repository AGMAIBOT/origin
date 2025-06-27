# constants.py (ОБНОВЛЕННАЯ ВЕРСИЯ)

# --- Константы для управления состояниями пользователя (конечный автомат) ---
# Это "законы физики" для FSM. Их изменение требует изменения кода.
STATE_NONE = 0
STATE_WAITING_FOR_NEW_CHAR_NAME = 1
STATE_WAITING_FOR_NEW_CHAR_PROMPT = 2
STATE_EDITING_CHAR_NAME = 3
STATE_EDITING_CHAR_PROMPT = 4
STATE_WAITING_FOR_IMAGE_PROMPT = 5

# --- Константы для ключей в context.user_data ---
# Это внутренние ключи, на которые завязан код.
CUSTOM_CHARACTERS_DATA_KEY = "custom_characters"
CURRENT_CHAR_CATEGORY_KEY = "current_character_category"
# Временные данные для создания/редактирования
TEMP_CHAR_ID = "temp_char_id"
TEMP_CHAR_NAME = "temp_char_name"
TEMP_CHAR_PROMPT = "temp_char_prompt"
CURRENT_IMAGE_GEN_PROVIDER_KEY = "current_image_gen_provider"

# Ключи для пагинации
CURRENT_CHAR_VIEW_PAGE_KEY = "current_character_view_page"
CURRENT_CHAR_MANAGE_PAGE_KEY = "current_character_manage_page"
MANAGE_MODE_KEY = "manage_mode"

# --- Фундаментальные идентификаторы тарифов и AI ---
# Это не настройки, а внутренние имена, которые использует код.
# Например, в базе данных хранится 'free', 'lite', 'pro'.
TIER_FREE = 'free'
TIER_LITE = 'lite'
TIER_PRO = 'pro'

# Логические идентификаторы AI провайдеров.
GEMINI_STANDARD = "gemini_standard"
DEEPSEEK_CHAT = "deepseek_chat"
GPT_3_5_TURBO = "gpt_3_5_turbo"
GPT_4_OMNI = "gpt_4_omni"
GPT_O4_MINI = "gpt_4o_mini"
OPENROUTER_DEEPSEEK = "openrouter_deepseek"
OPENROUTER_GEMINI_2_FLASH = "openrouter_gemini_2_flash"
IMAGE_GEN_DALL_E_3 = "image_gen_dalle3"
IMAGE_GEN_YANDEXART = "image_gen_yandexart"