# ai_clients/gpt_client.py (НОВЫЙ ФАЙЛ)

import logging
from typing import List, Dict, Tuple
from PIL.Image import Image
from openai import AsyncOpenAI

from .base_client import BaseAIClient

logger = logging.getLogger(__name__)

class GPTClient(BaseAIClient):
    @property
    def supports_characters(self) -> bool:
        return False
    
    def __init__(self, api_key: str, system_instruction: str, model_name: str):
        # Для OpenAI мы используем стандартный клиент без указания base_url
        self._client = AsyncOpenAI(api_key=api_key)
        self._model_name = model_name
        self._system_instruction = {"role": "system", "content": system_instruction}
        logger.info(f"Клиент OpenAI GPT инициализирован с моделью: '{model_name}'.")

    async def get_text_response(self, chat_history: List[Dict], user_prompt: str) -> Tuple[str, int]:
        messages = [self._system_instruction]
        for msg in chat_history:
            if not (msg.get("parts") and msg["parts"][0]):
                continue
            
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
            logger.error(f"Ошибка от OpenAI API: {e}", exc_info=True)
            return f"Произошла ошибка при обращении к GPT: {e}", 0

    async def get_image_response(self, text_prompt: str, image: Image) -> Tuple[str, int]:
        # GPT-4 Omni (и другие vision-модели OpenAI) поддерживают изображения,
        # но формат запроса отличается. Для простоты сейчас мы сделаем заглушку,
        # как и для DeepSeek. Полноценную поддержку можно будет добавить позже.
        logger.warning("Попытка использовать обработку изображений с GPT, которая пока не реализована в этом клиенте.")
        return "К сожалению, обработка изображений для моделей GPT в данный момент не реализована в боте.", 0