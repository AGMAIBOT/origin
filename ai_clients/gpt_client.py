# ai_clients/gpt_client.py

import logging
from typing import List, Dict, Tuple
from PIL.Image import Image
# <<< ИЗМЕНЕНИЕ: openai.PermissionDeniedError импортируем для лучшей обработки ошибок >>>
from openai import AsyncOpenAI, Timeout, PermissionDeniedError
import base64
from io import BytesIO

from .base_client import BaseAIClient
from .aiutils import prepare_openai_history
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
    def __init__(self, api_key: str, system_instruction: str, model_name: str):
        self._client = AsyncOpenAI(
            api_key=api_key,
            timeout=Timeout(60.0) 
        )
        self._model_name = model_name
        self._system_instruction_content = system_instruction
        logger.info(f"Клиент OpenAI GPT инициализирован с моделью: '{model_name}'.")

    async def get_text_response(self, chat_history: List[Dict], user_prompt: str) -> Tuple[str, int]:
        messages = prepare_openai_history(
            system_instruction_content=self._system_instruction_content,
            chat_history=chat_history,
            user_prompt=user_prompt
        )
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
        messages = prepare_openai_history(
            system_instruction_content=self._system_instruction_content,
            chat_history=chat_history,
            user_prompt=""
        )
        if not messages[-1]["content"]:
            messages.pop()
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

    # <<< ИЗМЕНЕНИЕ: Метод переписан для использования классического API DALL-E 3 (План Б) >>>
    async def generate_image(self, prompt: str) -> tuple[str | None, str | None]:
        """
        Генерирует изображение с помощью классического API DALL-E 3.
        Возвращает кортеж (image_url, error_message).
        В случае успеха image_url будет содержать ссылку на картинку, а error_message будет None.
        В случае ошибки image_url будет None, а error_message будет содержать текст ошибки.
        """
        logger.info(f"Запрос на генерацию изображения с моделью dall-e-3")
        try:
            # Вызываем другой, более простой и стабильный API для генерации изображений
            response = await self._client.images.generate(
                model="dall-e-3",     # Явно указываем модель для рисования
                prompt=prompt,
                n=1,
                size="1024x1024",     # Стандартный размер, можно выбрать и другие
                quality="standard",   # Можно поменять на "hd" для лучшего качества, но дороже
                response_format="url",# Мы хотим получить именно ссылку
            )

            # API возвращает прямую ссылку на сгенерированное изображение
            image_url = response.data[0].url
            if not image_url:
                 return None, "Не удалось сгенерировать изображение. API не вернул URL."

            return image_url, None # Успех!

        except PermissionDeniedError as e:
            logger.error(f"Ошибка доступа при генерации изображения через DALL-E 3 API: {e}", exc_info=True)
            return None, "Доступ к API генерации изображений запрещен. Проверьте ваш тарифный план и лимиты в OpenAI."
        except Exception as e:
            logger.error(f"Ошибка при генерации изображения через DALL-E 3 API: {e}", exc_info=True)
            return None, f"Произошла ошибка при обращении к DALL-E 3 API: {e}"