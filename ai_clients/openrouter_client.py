import logging
from typing import List, Dict, Tuple
from PIL.Image import Image
from openai import AsyncOpenAI, RateLimitError

import config # Импортируем наш конфиг
from .base_client import BaseAIClient

logger = logging.getLogger(__name__)

class OpenRouterClient(BaseAIClient):
    @property
    def supports_characters(self) -> bool:
        return False
    """
    Клиент для работы с моделями через сервис-посредник OpenRouter.
    """
    def __init__(self, api_key: str, system_instruction: str, model_name: str):
        self._client = AsyncOpenAI(
            api_key=api_key,
            base_url=config.OPENROUTER_API_BASE_URL # Используем URL из конфига
        )
        self._model_name = model_name
        self._system_instruction = {"role": "system", "content": system_instruction}
        
        # Готовим заголовки для OpenRouter
        self._extra_headers = {
            "HTTP-Referer": config.OPENROUTER_SITE_URL,
            "X-Title": config.OPENROUTER_SITE_NAME,
        }
        
        logger.info(f"Клиент OpenRouter инициализирован с моделью: '{model_name}'.")

    async def get_text_response(self, chat_history: List[Dict], user_prompt: str) -> Tuple[str, int]:
        messages = [self._system_instruction]
        for msg in chat_history:
            if not (msg.get("parts") and msg["parts"][0]):
                continue
            role = "assistant" if msg["role"] == "model" else msg["role"]
            messages.append({"role": role, "content": msg["parts"][0]})
        
        messages.append({"role": "user", "content": user_prompt})

        try:
            # <<< КЛЮЧЕВОЕ ИЗМЕНЕНИЕ: передаем extra_headers >>>
            response = await self._client.chat.completions.create(
                model=self._model_name,
                messages=messages,
                extra_headers=self._extra_headers
            )
            
            response_text = response.choices[0].message.content
            # OpenRouter может не возвращать токены в usage, добавляем проверку
            tokens_spent = response.usage.total_tokens if response.usage else 0
            
            return response_text, tokens_spent
            
        except RateLimitError as e:
            logger.warning(f"Достигнут Rate Limit для модели {self._model_name} через OpenRouter: {e}")
            
            # Пытаемся извлечь детальное сообщение от OpenRouter для пользователя
            error_details = "Сервер временно перегружен, попробуйте позже."
            if e.body and 'error' in e.body and e.body['error'].get('metadata', {}).get('raw'):
                error_details = f"Ошибка от провайдера: {e.body['error']['metadata']['raw']}"
            
            # Возвращаем пользователю понятное сообщение вместо падения бота
            return f"😔 К сожалению, модель сейчас недоступна. {error_details}", 0

        except Exception as e:
            logger.error(f"Ошибка от OpenRouter API: {e}", exc_info=True)
            return f"Произошла ошибка при обращении к OpenRouter: {e}", 0

    async def get_image_response(self, text_prompt: str, image: Image) -> Tuple[str, int]:
        # Пока оставляем заглушку, т.к. vision-модели у OpenRouter имеют свои особенности
        logger.warning("Попытка использовать обработку изображений с OpenRouter, которая не поддерживается.")
        return "К сожалению, выбранная модель AI (через OpenRouter) не умеет обрабатывать изображения.", 0