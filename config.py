# ПАГИНАЦИЯ, РЕФЛЕКТОРИНГ

from constants import (
    GEMINI_STANDARD, GPT_1, GPT_2,
    OPENROUTER_DEEPSEEK, OPENROUTER_GEMINI_2_FLASH
)
# --- Настройки AI моделей ---
GEMINI_MODEL = "gemini-1.5-flash-latest"
DEEPSEEK_CHAT_MODEL = "deepseek/deepseek-chat-v3-0324:free"
GPT_1_MODEL = "gpt-4.1-nano"
GPT_2_MODEL = "o4-mini-2025-04-16"
GPT_3_5_TURBO_MODEL = "gpt-3.5-turbo"
GEMINI_2_FLASH_EXP_MODEL = "google/gemini-2.0-flash-exp:free"


# [Dev-Ассистент]: ШАГ 1: Мастер-список всех моделей для "витрины" меню.
ALL_TEXT_MODELS_FOR_SELECTION = [
    {
        "provider_id": GPT_2, 
        "display_name": "GPT-o4-mini (умный, vision)"
    },
    {
        "provider_id": GPT_1, 
        "display_name": "GPT-4.1-nano (быстрый, vision)"
    },
    #{
    #   "provider_id": GEMINI_STANDARD, 
    #    "display_name": "Gemini 1.5 Flash (vision)"
    #},
    {
        "provider_id": OPENROUTER_DEEPSEEK, 
        "display_name": "DeepSeek (OpenRouter)"
    },
    #{
    #    "provider_id": OPENROUTER_GEMINI_2_FLASH, 
    #    "display_name": "Gemini 2.0 Flash (Exp, OR)"
    #},
]

# --- Настройки тарифов ---
# [Dev-Ассистент]: ШАГ 2: Обновляем тарифы, добавляя "связку ключей" - available_providers.
SUBSCRIPTION_TIERS = {
    'free': {
        "name": "Бесплатный",
        "daily_limit": 50,
        "ai_provider": GPT_1,  # Модель по умолчанию для новых пользователей этого тарифа
        "available_providers": [      # Список доступных для выбора моделей
        GPT_1
        ],
        "can_use_vision": True,
    },
    'lite': {
        "name": "Lite",
        "daily_limit": 200,
        "ai_provider": GPT_1, # Модель по умолчанию
        "available_providers": [
            GPT_2,
            GPT_1,
            OPENROUTER_DEEPSEEK
        ],
        "can_use_vision": True,
    },
    'pro': {
        "name": "Pro",
        "daily_limit": None,
        "ai_provider": GPT_1, # Модель по умолчанию
        "available_providers": [      # Pro-пользователям доступны все модели из мастер-списка
            GPT_2,
            GPT_1,
            OPENROUTER_DEEPSEEK,
        ],
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
POST_PROCESSING_SHORT_THRESHOLD = 300 # Все, что НИЖЕ этого значения - короткий ответ (без кнопок).
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
    GPT_2: 25000,
    GPT_1: 25000,
    OPENROUTER_DEEPSEEK: 15000,
    OPENROUTER_GEMINI_2_FLASH: 30000,
}
# --- Настройки генерации изображений ---
# [Dev-Ассистент]: Лимит на количество символов в промпте для YandexArt.
# [Dev-Ассистент]: Мы вынесли его сюда, чтобы легко менять в одном месте.
YANDEXART_PROMPT_LIMIT = 500