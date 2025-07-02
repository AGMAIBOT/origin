# ПАГИНАЦИЯ, РЕФЛЕКТОРИНГ

from constants import (
    GEMINI_STANDARD, GPT_1, GPT_2,
    OPENROUTER_DEEPSEEK, OPENROUTER_GEMINI_2_FLASH,
    DALL_E_3_SIZE_1024X1024,DALL_E_3_SIZE_1024X1792,
    DALL_E_3_SIZE_1792X1024,YANDEXART_SIZE_1024X1024,
    YANDEXART_SIZE_1024X1792, YANDEXART_SIZE_1792X1024
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
        "daily_limit": 20,
        "ai_provider": GPT_1,  # Модель по умолчанию для новых пользователей этого тарифа
        "available_providers": [      # Список доступных для выбора моделей
        GPT_1
        ],
        "can_use_vision": True,
        # [Dev-Ассистент]: НОВЫЕ НАСТРОЙКИ КОНТЕКСТА
        "active_buffer_message_count": 19, # [Dev-Ассистент]: Количество сообщений в активном буфере
        "summarization_token_trigger": 5000, # [Dev-Ассистент]: Порог токенов для запуска суммаризации
        "max_llm_input_tokens": 8000, # [Dev-Ассистент]: Максимальный лимит токенов для LLM-запроса
    },
    'lite': {
        "name": "Lite",
        "daily_limit": 50,
        "ai_provider": GPT_1, # Модель по умолчанию
        "available_providers": [
            GPT_2,
            GPT_1,
            OPENROUTER_DEEPSEEK
        ],
        "can_use_vision": True,
        # [Dev-Ассистент]: НОВЫЕ НАСТРОЙКИ КОНТЕКСТА
        "active_buffer_message_count": 50, # [Dev-Ассистент]: Количество сообщений в активном буфере
        "summarization_token_trigger": 25000, # [Dev-Ассистент]: Порог токенов для запуска суммаризации
        "max_llm_input_tokens": 32000, # [Dev-Ассистент]: Максимальный лимит токенов для LLM-запроса
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
        # [Dev-Ассистент]: НОВЫЕ НАСТРОЙКИ КОНТЕКСТА
        "active_buffer_message_count": 100, # [Dev-Ассистент]: Количество сообщений в активном буфере
        "summarization_token_trigger": 50000, # [Dev-Ассистент]: Порог токенов для запуска суммаризации
        "max_llm_input_tokens": 100000, # [Dev-Ассистент]: Максимальный лимит токенов для LLM-запроса
    }
}
OPENROUTER_API_BASE_URL = "https://openrouter.ai/api/v1"
OPENROUTER_SITE_URL = "https://t.me/agmai_bot"
OPENROUTER_SITE_NAME = "AGMAI"

# --- Настройки истории чата ---
# [Dev-Ассистент]: Эти константы HISTORY_LIMIT_TRIGGER, HISTORY_TRIM_TO, DEFAULT_HISTORY_LIMIT
# [Dev-Ассистент]: теперь не используются для управления контекстом LLM,
# [Dev-Ассистент]: их заменили новые токен-ориентированные настройки в SUBSCRIPTION_TIERS.
# [Dev-Ассистент]: Могут быть удалены, если нет других зависимостей.
HISTORY_LIMIT_TRIGGER = 120  # При какой длине истории запускать обрезку
HISTORY_TRIM_TO = 70         # Сколько сообщений оставлять после обрезки
DEFAULT_HISTORY_LIMIT = 50   # Сколько последних сообщений отправлять в AI

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

# [Dev-Ассистент]: НОВАЯ КОНСТАНТА ДЛЯ РЕФЕРАЛЬНОЙ ПРОГРАММЫ
REFERRAL_PERCENTAGE = 10 # % от пополнения реферала, который получает реферер. (Например, 10 означает 10%)

# [Dev-Ассистент]: Константа для курса доллара к AGM
USD_TO_AGM_RATE = 80 # 1 USD = 80 AGMcoin

# [Dev-Ассистент]: Стоимость DALL-E 3 Standard качества в USD по разрешениям
DALL_E_3_PRICING = {
    DALL_E_3_SIZE_1024X1024: {"display_name": "1:1", "cost_usd": 0.08},
    DALL_E_3_SIZE_1024X1792: {"display_name": "9:16", "cost_usd": 0.16},
    DALL_E_3_SIZE_1792X1024: {"display_name": "16:9", "cost_usd": 0.16},
}
# [Dev-Ассистент]: Разрешение DALL-E 3 по умолчанию
DALL_E_3_DEFAULT_RESOLUTION = DALL_E_3_SIZE_1024X1792

# [Dev-Ассистент]: Стоимость YandexArt Standard качества в USD по разрешениям
YANDEXART_PRICING = { # [Dev-Ассистент]: НОВАЯ КОНСТАНТА
    YANDEXART_SIZE_1024X1024: {"display_name": "1:1", "cost_usd": 0.05}, # 1.6 AGM
    YANDEXART_SIZE_1024X1792: {"display_name": "9:16", "cost_usd": 0.05}, # 3.2 AGM
    YANDEXART_SIZE_1792X1024: {"display_name": "16:9", "cost_usd": 0.05}, # 3.2 AGM
}

# [Dev-Ассистент]: Разрешение YandexArt по умолчанию
YANDEXART_DEFAULT_RESOLUTION = YANDEXART_SIZE_1024X1792 # [Dev-Ассистент]: НОВАЯ КОНСТАНТА

# [Dev-Ассистент]: НАСТРОЙКИ ДЛЯ СУММАРИЗАТОРА (перенесены из main.py)
SUMMARIZATION_PROMPT = """
Ты — высококвалифицированный, беспристрастный суммаризатор. Твоя основная задача — выполнить строгое, фактологическое, неинтерпретативное резюмирование предоставленного диалога. Резюме должно содержать исключительно информацию из диалога и обязано явно идентифицировать все:
1.  Ключевые факты и данные, включая их контекст и, при наличии, количественные показатели.
2.  Принятые решения, с указанием их сути, условий и, применимо, ответственных сторон.
3.  Достигнутые договоренности и взаимные обязательства, включая сроки исполнения и вовлеченные стороны.
4.  Центральные темы обсуждения и основные аргументы, приведшие к решениям или договоренностям.

Категорически не допускается включение личных интерпретаций, выводов, оценок, предложений или любой информации, не содержащейся напрямую в исходном тексте диалога.

Цель: Достичь максимальной информационной плотности и абсолютной точности при минимально возможном объеме текста, обеспечивающего полное и неискаженное сохранение смысла и всех перечисленных ключевых деталей.

Формат ответа: Единый, логически связный, повествовательный текст.
"""
SUMMARIZATION_MODEL_NAME = GPT_1 # [Dev-Ассистент]: Используем GPT_1 (gpt-4.1-nano) для суммаризации