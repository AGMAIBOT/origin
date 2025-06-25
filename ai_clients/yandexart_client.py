# ai_clients/yandexart_client.py (ИСПРАВЛЕННАЯ ВЕРСИЯ)

import os
import logging
import asyncio
import time
import json
from typing import Tuple

# <<< ИЗМЕНЕНИЕ: Добавляем недостающий импорт >>>
import base64
import aiohttp 

logger = logging.getLogger(__name__)

IAM_TOKEN_URL = "https://iam.api.yandex.net/iam/v1/tokens"
IMAGE_API_URL = "https://llm.api.yandex.net/foundationModels/v1/imageGenerationAsync"

class YandexArtClient:
    def __init__(self, folder_id: str, oauth_token: str = None, api_key_id: str = None, api_secret: str = None):
        if not folder_id:
            raise ValueError("Yandex Folder ID не указан.")
        if not oauth_token and not (api_key_id and api_secret):
            raise ValueError("Необходимо указать либо OAuth-токен, либо API-ключ и секрет для Yandex.")
            
        self._folder_id = folder_id
        self._oauth_token = oauth_token
        self._api_key_id = api_key_id
        self._api_secret = api_secret
        
        self._iam_token = None
        self._iam_token_expires_at = 0

    async def _get_iam_token(self) -> str:
        """Получает или обновляет IAM-токен."""
        if self._iam_token and self._iam_token_expires_at > time.time() + 60:
            return self._iam_token

        logger.info("Получение нового IAM-токена Yandex...")
        headers = {"Content-Type": "application/json"}
        
        # Для простоты старта мы используем OAuth. В реальном проде лучше JWT.
        if not self._oauth_token:
             raise ValueError("Для данной реализации требуется OAuth-токен.")
        payload = {"yandexPassportOauthToken": self._oauth_token}

        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(IAM_TOKEN_URL, headers=headers, json=payload) as resp:
                    resp.raise_for_status()
                    data = await resp.json()
                    self._iam_token = data['iamToken']
                    self._iam_token_expires_at = time.time() + (3600 * 6)
                    logger.info("Новый IAM-токен успешно получен.")
                    return self._iam_token
            except aiohttp.ClientError as e:
                logger.error(f"Ошибка получения IAM-токена: {e}")
                raise

    async def generate_image(self, prompt: str) -> Tuple[bytes | None, str | None]:
        """
        Генерирует изображение через YandexArt API.
        Возвращает кортеж (image_bytes, error_message).
        """
        try:
            iam_token = await self._get_iam_token()
        except Exception as e:
            return None, f"Ошибка аутентификации в Yandex: {e}"

        headers = {
            "Authorization": f"Bearer {iam_token}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "modelUri": f"art://{self._folder_id}/yandex-art/latest",
            "messages": [{"text": prompt, "weight": 1}],
            "generationOptions": {"seed": int(time.time())}
        }

        async with aiohttp.ClientSession() as session:
            try:
                logger.info("Отправка запроса на генерацию в YandexArt...")
                async with session.post(IMAGE_API_URL, headers=headers, json=payload) as resp:
                    resp.raise_for_status()
                    operation_data = await resp.json()
                    operation_id = operation_data.get("id")
                    if not operation_id:
                        return None, "API не вернул ID операции."
                
                logger.info(f"Начало опроса операции: {operation_id}")
                operation_url = f"https://operation.api.yandex.net/operations/{operation_id}"
                
                for _ in range(60): 
                    await asyncio.sleep(2)
                    async with session.get(operation_url, headers=headers) as op_resp:
                        op_resp.raise_for_status()
                        op_data = await op_resp.json()
                        if op_data.get("done"):
                            logger.info("Генерация завершена успешно.")
                            image_base64 = op_data.get("response", {}).get("image")
                            if not image_base64:
                                return None, "Операция завершена, но не содержит изображения."
                            
                            # Теперь base64.b64decode будет работать
                            image_bytes = base64.b64decode(image_base64)
                            return image_bytes, None
                
                return None, "Время ожидания генерации истекло."

            except aiohttp.ClientError as e:
                error_body = await e.response.text()
                logger.error(f"Ошибка API YandexArt: {e}. Тело ответа: {error_body}")
                return None, f"Ошибка API YandexArt: {e.status} - {error_body}"
            except Exception as e:
                logger.error(f"Неизвестная ошибка при работе с YandexArt: {e}", exc_info=True)
                return None, f"Неизвестная ошибка: {e}"