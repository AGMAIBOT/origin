# ai_clients/factory.py (ИСПРАВЛЕННАЯ ВЕРСИЯ)

import os
from typing import NamedTuple
from .base_client import BaseAIClient
from .gemini_client import GeminiClient
from .deepseek_client import DeepSeekClient
from .gpt_client import GPTClient
from .openrouter_client import OpenRouterClient
from constants import *
import config

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

class AIClientCapabilities(NamedTuple):
    """Описывает возможности и ограничения конкретного AI клиента."""
    client: BaseAIClient
    supports_vision: bool = False
    file_char_limit: int = 0

def get_ai_client_with_caps(provider_identifier: str, system_instruction: str) -> AIClientCapabilities:
    """
    Фабрика, которая создает AI клиент и возвращает его вместе с его возможностями.
    """
    provider_identifier = provider_identifier.lower()

    # --- Маршрутизация к Gemini ---
    if provider_identifier == GEMINI_STANDARD:
        if not GEMINI_API_KEY: raise ValueError("API ключ для Gemini не найден.")
        
        # Просто берем единственную модель Gemini из конфига.
        model_name = config.GEMINI_MODEL
        
        client = GeminiClient(api_key=GEMINI_API_KEY, system_instruction=system_instruction, model_name=model_name, vision_model_name=model_name)
        
        return AIClientCapabilities(
            client=client,
            supports_vision=True,
            file_char_limit=config.FILE_PROCESSING_LIMITS.get(provider_identifier, 0)
        )
        
    # --- Маршрутизация к DeepSeek ---
    elif provider_identifier == DEEPSEEK_CHAT:
        if not DEEPSEEK_API_KEY: raise ValueError("API ключ для DeepSeek не найден.")
        client = DeepSeekClient(api_key=DEEPSEEK_API_KEY, system_instruction=system_instruction, model_name=config.DEEPSEEK_CHAT_MODEL)
        return AIClientCapabilities(
            client=client,
            supports_vision=False,
            file_char_limit=config.FILE_PROCESSING_LIMITS.get(provider_identifier, 0)
        )
    
    # --- Маршрутизация к OpenRouter ---
    elif provider_identifier == OPENROUTER_DEEPSEEK:
        if not OPENROUTER_API_KEY: raise ValueError("API ключ для OpenRouter не найден.")
        client = OpenRouterClient(api_key=OPENROUTER_API_KEY, system_instruction=system_instruction, model_name=config.DEEPSEEK_CHAT_MODEL)
        return AIClientCapabilities(client=client)

    # --- Маршрутизация к OpenAI GPT ---
    elif provider_identifier == GPT_4_OMNI:
        if not OPENAI_API_KEY: raise ValueError("API ключ для OpenAI не найден.")
        client = GPTClient(api_key=OPENAI_API_KEY, system_instruction=system_instruction, model_name="GPT_4_OMNI_MODEL")
        return AIClientCapabilities(
            client=client,
            supports_vision=True, 
            file_char_limit=config.FILE_PROCESSING_LIMITS.get(provider_identifier, 0)
        )
    
    # --- Заглушка для других GPT ---
    elif provider_identifier == GPT_3_5_TURBO:
        if not OPENAI_API_KEY: raise ValueError("API ключ для OpenAI не найден.")
        client = GPTClient(api_key=OPENAI_API_KEY, system_instruction=system_instruction, model_name="GPT_3_5_TURBO_MODEL")
        return AIClientCapabilities(client=client)
        
    else:
        # Если ни один из if/elif не сработал, вызываем ошибку.
        raise ValueError(f"Неизвестный или неподдерживаемый идентификатор провайдера: '{provider_identifier}'")