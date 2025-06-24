# ai_clients/gpt_client.py

import logging
from typing import List, Dict, Tuple
from PIL.Image import Image
from openai import AsyncOpenAI, Timeout
import base64
from io import BytesIO

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


class GPTClient(BaseAIClient):
    @property
    def supports_characters(self) -> bool:
        # GPT-модели поддерживают системные инструкции, так что это можно будет
        # в будущем доработать для более глубокой интеграции. Пока оставляем False для простоты.
        return False
    
    # V-- ВОТ НЕДОСТАЮЩИЙ БЛОК, КОТОРЫЙ НУЖНО ДОБАВИТЬ --V
    def __init__(self, api_key: str, system_instruction: str, model_name: str):
        """
        Конструктор класса. Инициализирует клиент OpenAI и сохраняет настройки.
        """
        self._client = AsyncOpenAI(
            api_key=api_key,
            # Устанавливаем таймаут в 60 секунд. Этого должно хватить для большинства запросов.
            timeout=Timeout(60.0) 
        )
        self._model_name = model_name
        self._system_instruction = {"role": "system", "content": system_instruction}
        logger.info(f"Клиент OpenAI GPT инициализирован с моделью: '{model_name}'.")
    # ^-- КОНЕЦ БЛОКА, КОТОРЫЙ НУЖНО БЫЛО ДОБАВИТЬ --^
    
    async def get_text_response(self, chat_history: List[Dict], user_prompt: str) -> Tuple[str, int]:
        """Получает текстовый ответ от AI."""
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
            tokens_spent = response.usage.total_tokens if response.usage else 0
            return response_text, tokens_spent
        except Exception as e:
            logger.error(f"Ошибка от OpenAI API: {e}", exc_info=True)
            return f"Произошла ошибка при обращении к GPT: {e}", 0

    async def get_image_response(self, chat_history: List[Dict], text_prompt: str, image: Image) -> Tuple[str, int]:
        logger.info(f"Запрос к GPT Vision с моделью {self._model_name}")
        base64_image = _pil_to_base64(image)
        
        messages = [self._system_instruction]
        
        for msg in chat_history:
            if not (msg.get("parts") and msg["parts"][0]):
                continue
            role = "assistant" if msg["role"] == "model" else msg["role"]
            messages.append({"role": role, "content": msg["parts"][0]})
            
        messages.append({
            "role": "user",
            "content": [
                {"type": "text", "text": text_prompt},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}
            ]
        })

        try:
            response = await self._client.chat.completions.create(
                model=self._model_name,
                messages=messages,
                max_tokens=2048
            )
            response_text = response.choices[0].message.content
            tokens_spent = response.usage.total_tokens if response.usage else 0
            return response_text, tokens_spent
        except Exception as e:
            logger.error(f"Ошибка от OpenAI Vision API: {e}", exc_info=True)
            return f"Произошла ошибка при обращении к GPT Vision: {e}", 0