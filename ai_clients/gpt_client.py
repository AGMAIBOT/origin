import logging
from typing import List, Dict, Tuple
from PIL.Image import Image
from openai import AsyncOpenAI

# <<< НОВЫЕ ИМПОРТЫ для работы с изображениями >>>
import base64
from io import BytesIO

from .base_client import BaseAIClient

logger = logging.getLogger(__name__)

# <<< НОВАЯ ВСПОМОГАТЕЛЬНАЯ ФУНКЦИЯ >>>
def _pil_to_base64(image: Image) -> str:
    """Конвертирует объект PIL Image в строку Base64."""
    # Создаем буфер в памяти
    buffered = BytesIO()
    # Конвертируем изображение в RGB, если у него есть альфа-канал (прозрачность),
    # так как JPEG не поддерживает его.
    if image.mode == 'RGBA':
        image = image.convert('RGB')
    # Сохраняем изображение в буфер в формате JPEG.
    # Это уменьшает размер передаваемых данных.
    image.save(buffered, format="JPEG")
    # Получаем байты из буфера и кодируем их в Base64.
    img_bytes = buffered.getvalue()
    return base64.b64encode(img_bytes).decode('utf-8')


class GPTClient(BaseAIClient):
    # ... (init и supports_characters без изменений) ...

    # ... (get_text_response без изменений) ...

    # <<< ПОЛНОСТЬЮ ПЕРЕПИСАННЫЙ МЕТОД get_image_response >>>
    async def get_image_response(self, text_prompt: str, image: Image) -> Tuple[str, int]:
        """
        Получает текстовый ответ от GPT-4 Omni на основе изображения и текста.
        """
        logger.info(f"Запрос к GPT Vision с моделью {self._model_name}")
        base64_image = _pil_to_base64(image)
        
        # Формируем сообщение в формате, который ожидает OpenAI API для vision
        messages = [
            self._system_instruction,
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": text_prompt
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            # Передаем изображение напрямую в формате Base64
                            "url": f"data:image/jpeg;base64,{base64_image}"
                        }
                    }
                ]
            }
        ]

        try:
            response = await self._client.chat.completions.create(
                model=self._model_name,
                messages=messages,
                max_tokens=2048 # Можно задать лимит на токены в ответе
            )
            
            response_text = response.choices[0].message.content
            tokens_spent = response.usage.total_tokens if response.usage else 0
            
            return response_text, tokens_spent
            
        except Exception as e:
            logger.error(f"Ошибка от OpenAI Vision API: {e}", exc_info=True)
            return f"Произошла ошибка при обращении к GPT Vision: {e}", 0