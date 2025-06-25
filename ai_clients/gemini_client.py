# ai_clients/gemini_client.py

import logging
from typing import List, Dict, Tuple
from PIL.Image import Image

import google.generativeai as genai
from google.generativeai.types import GenerationConfig, generation_types
from google.api_core.exceptions import ResourceExhausted

from .base_client import BaseAIClient

logger = logging.getLogger(__name__)

class GeminiClient(BaseAIClient):
    
    def __init__(self, api_key: str, system_instruction: str, model_name: str, vision_model_name: str):
        try:
            genai.configure(api_key=api_key)
        except Exception as e:
            logger.error(f"Ошибка конфигурации Gemini API: {e}")
            raise

        self._system_instruction = system_instruction
        self._generation_config = GenerationConfig(temperature=0.9, top_p=1, top_k=1, max_output_tokens=2048)
        
        # <<< ИЗМЕНЕНИЕ 1: Смягчаем настройки безопасности >>>
        self._safety_settings = [
            # Меняем порог блокировки на "Блокировать только высокий".
            {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_ONLY_HIGH"},
            {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_ONLY_HIGH"},
            {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_ONLY_HIGH"},
            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_ONLY_HIGH"},
        ]
        
        self._text_model = self._create_model(model_name)
        self._vision_model = self._create_model(vision_model_name)
        
        logger.info(f"Клиент Gemini инициализирован с моделями: текст='{model_name}', vision='{vision_model_name}'.")

    def _create_model(self, model_name: str) -> genai.GenerativeModel:
        return genai.GenerativeModel(
            model_name=model_name,
            generation_config=self._generation_config,
            system_instruction=self._system_instruction,
            safety_settings=self._safety_settings
        )

    async def get_text_response(self, chat_history: List[Dict], user_prompt: str) -> Tuple[str, int]:
        full_history = chat_history + [{"role": "user", "parts": [user_prompt]}]
        try:
            response = await self._text_model.generate_content_async(full_history)

            # <<< ИЗМЕНЕНИЕ 2: Проверяем, не заблокирован ли ответ ПЕРЕД тем, как его читать >>>
            if not response.parts:
                # Ответ пустой. Проверяем причину.
                finish_reason = response.candidates[0].finish_reason if response.candidates else "UNKNOWN"
                if finish_reason == generation_types.FinishReason.SAFETY:
                    logger.warning(f"Запрос заблокирован фильтрами безопасности Gemini. Рейтинги: {response.prompt_feedback.safety_ratings}")
                    return "К сожалению, ваш запрос или содержимое файла было заблокировано внутренними фильтрами безопасности Gemini. Пожалуйста, попробуйте переформулировать его.", 0
                else:
                    logger.warning(f"Gemini вернул пустой ответ. Причина: {finish_reason.name if hasattr(finish_reason, 'name') else finish_reason}")
                    return f"ИИ не смог сгенерировать ответ (причина: {finish_reason.name if hasattr(finish_reason, 'name') else finish_reason}). Попробуйте еще раз.", 0
            
            # Если все в порядке, возвращаем текст
            return response.text, response.usage_metadata.total_token_count

        except Exception as e:
            logger.error(f"Ошибка от Gemini (текст): {e}", exc_info=True)
            # Перебрасываем ошибку выше, чтобы ее обработал main.py и сообщил пользователю
            raise

    async def get_image_response(self, chat_history: List[Dict], text_prompt: str, image: Image) -> Tuple[str, int]:
        full_request_content = chat_history + [
            {"role": "user", "parts": [text_prompt, image]}
        ]

        try:
            response = await self._vision_model.generate_content_async(full_request_content)
            
            if not response.parts:
                finish_reason = response.candidates[0].finish_reason if response.candidates else "UNKNOWN"
                if finish_reason == generation_types.FinishReason.SAFETY:
                    logger.warning(f"Запрос с изображением заблокирован фильтрами безопасности Gemini. Рейтинги: {response.prompt_feedback.safety_ratings}")
                    return "К сожалению, ваше изображение или запрос были заблокированы внутренними фильтрами безопасности Gemini. Пожалуйста, попробуйте другое изображение или запрос.", 0
                else:
                    logger.warning(f"Gemini вернул пустой ответ на изображение. Причина: {finish_reason.name if hasattr(finish_reason, 'name') else finish_reason}")
                    return f"ИИ не смог обработать изображение (причина: {finish_reason.name if hasattr(finish_reason, 'name') else finish_reason}).", 0

            return response.text, response.usage_metadata.total_token_count
        except Exception as e:
            logger.error(f"Ошибка от Gemini (vision): {e}", exc_info=True)
            raise