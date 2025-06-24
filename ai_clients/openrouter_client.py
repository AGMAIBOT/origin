# ai_clients/openrouter_client.py

import logging
from typing import List, Dict, Tuple
from PIL.Image import Image
from openai import AsyncOpenAI, RateLimitError, Timeout
import base64
from io import BytesIO

import config 
from .base_client import BaseAIClient

logger = logging.getLogger(__name__)

def _pil_to_base64(image: Image) -> str:
    """Конвертирует объект PIL Image в строку Base64."""
    buffered = BytesIO()
    if image.mode == 'RGBA':
        image = image.convert('RGB')
    image.save(buffered, format="JPEG")
    img_bytes = buffered.getvalue()
    return base64.b64encode(img_bytes).decode('utf-8')


class OpenRouterClient(BaseAIClient):
    @property
    def supports_characters(self) -> bool:
        return False

    # V-- ВОТ НЕДОСТАЮЩИЙ КОНСТРУКТОР, КОТОРЫЙ ВСЕ ИСПРАВИТ --V
    def __init__(self, api_key: str, system_instruction: str, model_name: str):
        """
        Конструктор класса. Инициализирует клиент для OpenRouter.
        """
        self._client = AsyncOpenAI(
            api_key=api_key,
            base_url=config.OPENROUTER_API_BASE_URL,
            # Устанавливаем таймаут и здесь
            timeout=Timeout(60.0)
        )
        self._model_name = model_name
        self._system_instruction = {"role": "system", "content": system_instruction}
        
        self._extra_headers = {
            "HTTP-Referer": config.OPENROUTER_SITE_URL,
            "X-Title": config.OPENROUTER_SITE_NAME,
        }
        
        logger.info(f"Клиент OpenRouter инициализирован с моделью: '{model_name}'.")
    # ^-- КОНЕЦ КОНСТРУКТОРА --^

    async def get_text_response(self, chat_history: List[Dict], user_prompt: str) -> Tuple[str, int]:
        # ... (этот метод уже был правильным, оставляем его без изменений) ...
        messages = [self._system_instruction]
        for msg in chat_history:
            if not (msg.get("parts") and msg["parts"][0]):
                continue
            role = "assistant" if msg["role"] == "model" else msg["role"]
            messages.append({"role": role, "content": msg["parts"][0]})
        messages.append({"role": "user", "content": user_prompt})
        try:
            response = await self._client.chat.completions.create(model=self._model_name, messages=messages, extra_headers=self._extra_headers)
            response_text = response.choices[0].message.content
            tokens_spent = response.usage.total_tokens if response.usage else 0
            return response_text, tokens_spent
        except RateLimitError as e:
            logger.warning(f"Достигнут Rate Limit для модели {self._model_name} через OpenRouter: {e}")
            error_details = "Сервер временно перегружен, попробуйте позже."
            if e.body and 'error' in e.body and e.body['error'].get('metadata', {}).get('raw'):
                error_details = f"Ошибка от провайдера: {e.body['error']['metadata']['raw']}"
            return f"😔 К сожалению, модель сейчас недоступна. {error_details}", 0
        except Exception as e:
            logger.error(f"Ошибка от OpenRouter API: {e}", exc_info=True)
            return f"Произошла ошибка при обращении к OpenRouter: {e}", 0

    async def get_image_response(self, chat_history: List[Dict], text_prompt: str, image: Image) -> Tuple[str, int]:
        # ... (этот метод тоже уже был правильным, оставляем без изменений) ...
        logger.info(f"Запрос к Vision модели {self._model_name} через OpenRouter")
        base64_image = _pil_to_base64(image)
        messages = [self._system_instruction]
        for msg in chat_history:
            if not (msg.get("parts") and msg["parts"][0]):
                continue
            role = "assistant" if msg["role"] == "model" else msg["role"]
            messages.append({"role": role, "content": msg["parts"][0]})
        messages.append({"role": "user", "content": [{"type": "text", "text": text_prompt}, {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}]})
        try:
            response = await self._client.chat.completions.create(model=self._model_name, messages=messages, max_tokens=2048, extra_headers=self._extra_headers)
            response_text = response.choices[0].message.content
            tokens_spent = response.usage.total_tokens if response.usage else 0
            return response_text, tokens_spent
        except RateLimitError as e:
            logger.warning(f"Достигнут Rate Limit для модели {self._model_name} через OpenRouter: {e}")
            error_details = "Сервер временно перегружен, попробуйте позже."
            if e.body and 'error' in e.body and e.body['error'].get('metadata', {}).get('raw'):
                error_details = f"Ошибка от провайдера: {e.body['error']['metadata']['raw']}"
            return f"😔 К сожалению, модель сейчас недоступна. {error_details}", 0
        except Exception as e:
            logger.error(f"Ошибка от OpenRouter Vision API: {e}", exc_info=True)
            return f"Произошла ошибка при обращении к OpenRouter Vision: {e}", 0