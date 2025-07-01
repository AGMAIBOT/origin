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
LAST_IMAGE_PROMPT_KEY = "last_image_prompt"
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
GPT_1 = "gpt_4_nano"
GPT_2 = "gpt_o4_mini"
OPENROUTER_DEEPSEEK = "openrouter_deepseek"
OPENROUTER_GEMINI_2_FLASH = "openrouter_gemini_2_flash"
IMAGE_GEN_DALL_E_3 = "image_gen_dalle3"
IMAGE_GEN_YANDEXART = "image_gen_yandexart"

# Константы для пост-обработки текста.
LAST_RESPONSE_KEY = "last_response_text" # Ключ для хранения последнего ответа AI
# Ключи для callback_data
ACTION_SHORTEN = "action_shorten"
ACTION_EXPAND = "action_expand"
ACTION_REPHRASE = "action_rephrase"
PROFILE_HUB_SETTINGS = "profile_hub_settings"
PROFILE_HUB_WALLET = "profile_hub_wallet"
PROFILE_HUB_SHOP = "profile_hub_shop"

WALLET_HUB = "wallet_hub" # Для перехода в само меню кошелька (после нажатия "Кошелек" из профиля)
WALLET_TOPUP_START = "wallet_topup_start"
WALLET_REFERRAL_PROGRAM = "wallet_referral_program"
WALLET_BACK_TO_PROFILE = "wallet_back_to_profile"
# [Dev-Ассистент]: НОВЫЕ КОНСТАНТЫ ДЛЯ ТИПОВ ТРАНЗАКЦИЙ (для БД)
TRANSACTION_TYPE_TOPUP = "topup"
TRANSACTION_TYPE_REQUEST_COST = "request_cost" # Для будущих списаний за запросы
TRANSACTION_TYPE_REFERRAL_BONUS = "referral_bonus"
TRANSACTION_TYPE_PURCHASE = "purchase" # Для будущих покупок
TRANSACTION_TYPE_REFERRAL_COMMISSION = "referral_commission" # <<< [Dev-Ассистент]: НОВАЯ КОНСТАНТА

# Кнопки в меню настроек
SETTINGS_BACK_TO_PROFILE_HUB = "settings_back_to_profile_hub"
SETTINGS_OUTPUT_FORMAT = "settings_output_format"

# Кнопки в меню формата вывода
FORMAT_SET_TEXT = "format_set_text"
FORMAT_SET_TXT = "format_set_txt"
FORMAT_SET_PDF = "format_set_pdf" # Задел на будущее
FORMAT_BACK_TO_SETTINGS = "format_back_to_settings"

# Строковые идентификаторы форматов для БД
OUTPUT_FORMAT_TEXT = "text"
OUTPUT_FORMAT_TXT = "txt"
OUTPUT_FORMAT_PDF = "pdf"

# [Dev-Ассистент]: НОВЫЕ КОНСТАНТЫ ДЛЯ DALL-E 3 РАЗРЕШЕНИЙ И ОПЛАТЫ
DALL_E_3_SIZE_1024X1024 = "1024x1024"
DALL_E_3_SIZE_1024X1792 = "1024x1792"
DALL_E_3_SIZE_1792X1024 = "1792x1024"
CURRENT_DALL_E_3_RESOLUTION_KEY = "current_dalle3_resolution" # Ключ для user_data

# [Dev-Ассистент]: НОВАЯ КОНСТАНТА ДЛЯ ТИПОВ ТРАНЗАКЦИЙ (для БД)
TRANSACTION_TYPE_IMAGE_GEN_COST = "image_gen_cost"