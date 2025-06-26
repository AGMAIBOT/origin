# ai_clients/yandexart_client.py
# [Dev-Ассистент]: ВЕРСИЯ С УЛУЧШЕННОЙ, НАДЕЖНОЙ ОБРАБОТКОЙ ОШИБОК

import os
import logging
import asyncio
import time
import json
import base64
from typing import Tuple
import aiohttp

logger = logging.getLogger(__name__)

IMAGE_API_URL = "https://llm.api.cloud.yandex.net/foundationModels/v1/imageGenerationAsync"
OPERATION_API_URL_TEMPLATE = "https://operation.api.cloud.yandex.net/operations/{}"


class YandexArtClient:
    def __init__(self, folder_id: str, api_key: str):
        if not folder_id:
            raise ValueError("Yandex Folder ID не указан.")
        if not api_key:
            raise ValueError("Необходимо указать статический API-ключ для Yandex.")

        self._folder_id = folder_id
        self._api_key = api_key

    async def generate_image(self, prompt: str) -> Tuple[bytes | None, str | None]:
        headers = {
            "Authorization": f"Api-Key {self._api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "modelUri": f"art://{self._folder_id}/yandex-art/latest",
            "messages": [{"text": prompt, "weight": "1"}],
            "generationOptions": {
                "seed": int(time.time()),
                "aspectRatio": {
                    "widthRatio": "1",
                    "heightRatio": "1"
                }
            }
        }

        try:
            async with aiohttp.ClientSession() as session:
                # --- ЭТАП 1: ЗАПУСК ГЕНЕРАЦИИ ---
                logger.info("Отправка запроса на генерацию в YandexArt (метод Api-Key)...")
                async with session.post(IMAGE_API_URL, headers=headers, json=payload) as resp:
                    # [Dev-Ассистент]: КЛЮЧЕВОЕ ИЗМЕНЕНИЕ!
                    # Вместо resp.raise_for_status(), мы вручную проверяем статус.
                    # Это позволяет нам безопасно прочитать тело ошибки, если она есть.
                    if resp.status != 200:
                        error_body = await resp.text()
                        logger.error(
                            f"Ошибка при запуске генерации YandexArt ({resp.status}): {error_body}"
                        )
                        # [Dev-Ассистент]: Возвращаем пользователю осмысленную ошибку
                        return None, f"Ошибка от Yandex ({resp.status}): {error_body}"

                    operation_data = await resp.json()
                    operation_id = operation_data.get("id")
                    if not operation_id:
                        return None, "API не вернул ID операции."

                # --- ЭТАП 2: ОЖИДАНИЕ РЕЗУЛЬТАТА ---
                logger.info(f"Начало опроса операции: {operation_id}")
                operation_url = OPERATION_API_URL_TEMPLATE.format(operation_id)

                for _ in range(60):
                    await asyncio.sleep(2)
                    async with session.get(operation_url, headers=headers) as op_resp:
                        # [Dev-Ассистент]: Здесь применяем ту же логику безопасной проверки
                        if op_resp.status != 200:
                            error_body = await op_resp.text()
                            logger.error(
                                f"Ошибка при проверке статуса операции YandexArt ({op_resp.status}): {error_body}"
                            )
                            return None, f"Ошибка от Yandex ({op_resp.status}): {error_body}"
                        
                        op_data = await op_resp.json()
                        if op_data.get("done"):
                            logger.info("Генерация завершена успешно.")
                            if 'error' in op_data:
                                error_details = op_data['error']
                                logger.error(f"Операция завершилась с ошибкой: {error_details}")
                                return None, f"Ошибка от Yandex: {error_details.get('message', 'Неизвестная ошибка')}"
                            
                            image_base64 = op_data.get("response", {}).get("image")
                            if not image_base64:
                                return None, "Операция завершена, но не содержит изображения."

                            image_bytes = base64.b64decode(image_base64)
                            return image_bytes, None

                return None, "Время ожидания генерации истекло."

        # [Dev-Ассистент]: Теперь этот блок ловит только ошибки соединения, а не ошибки API
        except aiohttp.ClientConnectorError as e:
            logger.error(f"Ошибка соединения с YandexArt: {e}")
            return None, f"Не удалось подключиться к серверам Yandex. Ошибка: {e}"
        except Exception as e:
            logger.error(f"Неизвестная ошибка при работе с YandexArt: {e}", exc_info=True)
            return None, f"Неизвестная ошибка: {e}"