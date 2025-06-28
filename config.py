# ПАГИНАЦИЯ, РЕФЛЕКТОРИНГ

from constants import GEMINI_STANDARD, GPT_4_OMNI, GPT_O4_MINI, OPENROUTER_DEEPSEEK, OPENROUTER_GEMINI_2_FLASH

# --- Настройки AI моделей ---
# Имена моделей, которые мы используем. Легко поменять в одном месте.
GEMINI_MODEL = "gemini-1.5-flash-latest"
DEEPSEEK_CHAT_MODEL = "deepseek/deepseek-r1-0528:free"
GPT_4_OMNI_MODEL = "gpt-4.1-nano"
GPT_3_5_TURBO_MODEL = "gpt-3.5-turbo"
GEMINI_2_FLASH_EXP_MODEL = "google/gemini-2.0-flash-exp:free"
GPT_4O_MINI_MODEL = "o4-mini-2025-04-16"

# --- Настройки тарифов ---
# Это "правила игры" для каждого тарифа.
# Имена провайдеров (GEMINI_STANDARD) импортируются из constants.py,
# так как они являются частью "законов физики" приложения.

SUBSCRIPTION_TIERS = {
    'free': {
        "name": "Бесплатный",
        "daily_limit": 30,
        "ai_provider": GEMINI_STANDARD, 
        "can_use_vision": True,
    },
    'lite': {
        "name": "Lite",
        "daily_limit": 200,
        "ai_provider": GEMINI_STANDARD,
        "can_use_vision": True,
    },
    'pro': {
        "name": "Pro",
        "daily_limit": None,
        "ai_provider": GEMINI_STANDARD, # В будущем можно заменить на GEMINI_PREMIUM
        "can_use_vision": True,
    }
}

OPENROUTER_API_BASE_URL = "https://openrouter.ai/api/v1"
OPENROUTER_SITE_URL = "https://t.me/agmai_bot"
OPENROUTER_SITE_NAME = "AGMAI"

# --- Настройки истории чата ---
HISTORY_LIMIT_TRIGGER = 100  # При какой длине истории запускать обрезку
HISTORY_TRIM_TO = 50         # Сколько сообщений оставлять после обрезки
DEFAULT_HISTORY_LIMIT = 40   # Сколько последних сообщений отправлять в AI

# Настройки для контекстных кнопок пост-обработки.
# Границы длины ответа (в символах) для показа разных наборов кнопок.
POST_PROCESSING_SHORT_THRESHOLD = 200 # Все, что НИЖЕ этого значения - короткий ответ (без кнопок).
POST_PROCESSING_MEDIUM_THRESHOLD = 600 # Ответ между SHORT и MEDIUM - средний (кнопки "Раскрой", "Перефразируй").
POST_PROCESSING_LONG_THRESHOLD = 1000  # Ответ между MEDIUM и LONG - длинный (кнопки "Сократи", "Перефразируй").
# Все, что ВЫШЕ LONG_THRESHOLD, также считается длинным.

# --- Настройки меню и контента ---
CHARACTERS_PER_PAGE = 8      # Количество кнопок с персонажами на одной странице
ABSOLUTE_MAX_FILE_CHARS = 30000 # Максимальное кол-во символов в .txt файле с промптом

FILE_PROCESSING_LIMITS = {
    # Для Gemini оставляем большой лимит, так как у него огромное контекстное окно
    GEMINI_STANDARD: 30000,
    
    # Для GPT-4o ставим более консервативный лимит, чтобы избежать ошибок
    # и больших затрат. 25000 символов ~ 6-8 тыс. токенов.
    GPT_O4_MINI: 25000,
    GPT_4_OMNI: 25000,
    OPENROUTER_DEEPSEEK: 15000,
    OPENROUTER_GEMINI_2_FLASH: 30000,
}
# --- Настройки генерации изображений ---
# [Dev-Ассистент]: Лимит на количество символов в промпте для YandexArt.
# [Dev-Ассистент]: Мы вынесли его сюда, чтобы легко менять в одном месте.
YANDEXART_PROMPT_LIMIT = 500