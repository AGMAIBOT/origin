# ai_clients/deepseek_client.py (НОВЫЙ ФАЙЛ)

import logging
from typing import List, Dict, Tuple
from PIL.Image import Image
from openai import AsyncOpenAI, Timeout  # Используем асинхронный клиент OpenAI

from .base_client import BaseAIClient

logger = logging.getLogger(__name__)

class DeepSeekClient(BaseAIClient):
    @property
    def supports_characters(self) -> bool:
        return False
    def __init__(self, api_key: str, system_instruction: str, model_name: str):
        # API DeepSeek совместимо с OpenAI, поэтому мы используем их клиент,
        # но указываем свой base_url и ключ.
        self._client = AsyncOpenAI(
            api_key=api_key,
            base_url="https://api.deepseek.com/v1",
            # Устанавливаем таймаут
            timeout=Timeout(60.0)
        )
        self._model_name = model_name
        self._system_instruction = {"role": "system", "content": system_instruction}
        logger.info(f"Клиент DeepSeek инициализирован с моделью: '{model_name}'.")

    async def get_text_response(self, chat_history: List[Dict], user_prompt: str) -> Tuple[str, int]:
        # Формат истории для OpenAI-совместимых API отличается от Gemini
        # Нам нужно преобразовать наш формат [{'role': 'user', 'parts': ['text']}]
        # в формат OpenAI [{'role': 'user', 'content': 'text'}]
        
        messages = [self._system_instruction]
        for msg in chat_history:
            # Пропускаем возможные "пустые" сообщения
            if not (msg.get("parts") and msg["parts"][0]):
                continue

            # <<< КЛЮЧЕВОЕ ИЗМЕНЕНИЕ: Преобразуем роль 'model' в 'assistant' >>>
            role = "assistant" if msg["role"] == "model" else msg["role"]
            
            messages.append({"role": role, "content": msg["parts"][0]})
        
        messages.append({"role": "user", "content": user_prompt})

        try:
            response = await self._client.chat.completions.create(
                model=self._model_name,
                messages=messages
            )
            
            response_text = response.choices[0].message.content
            tokens_spent = response.usage.total_tokens
            
            return response_text, tokens_spent
            
        except Exception as e:
            logger.error(f"Ошибка от DeepSeek API: {e}", exc_info=True)
            # Возвращаем дружелюбное сообщение об ошибке
            return f"Произошла ошибка при обращении к DeepSeek: {e}", 0

    async def get_image_response(self, text_prompt: str, image: Image) -> Tuple[str, int]:
        # Модель deepseek-chat не поддерживает обработку изображений.
        # Возвращаем понятный ответ и 0 токенов.
        logger.warning("Попытка использовать обработку изображений с DeepSeek, которая не поддерживается.")
        return "К сожалению, выбранная модель AI (DeepSeek) не умеет обрабатывать изображения.", 0