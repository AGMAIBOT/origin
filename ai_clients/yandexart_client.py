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
                    if resp.status != 200:
                        error_body = await resp.text()
                        logger.error(
                            f"Ошибка при запуске генерации YandexArt ({resp.status}): {error_body}"
                        )
                        return None, f"Ошибка от Yandex ({resp.status}): {error_body}"

                    operation_data = await resp.json()
                    operation_id = operation_data.get("id")
                    if not operation_id:
                        return None, "API не вернул ID операции."

                # --- ЭТАП 2: ОЖИДАНИЕ РЕЗУЛЬТАТА ---
                logger.info(f"Начало опроса операции: {operation_id}")
                operation_url = OPERATION_API_URL_TEMPLATE.format(operation_id)

                # [Dev-Ассистент]: КЛЮЧЕВОЕ ИСПРАВЛЕНИЕ!
                # [Dev-Ассистент]: Увеличиваем начальную задержку с 2 до 7 секунд.
                # [Dev-Ассистент]: Это даст системам Яндекса время для синхронизации
                # [Dev-Ассистент]: и предотвратит ошибку "Operation doesn't exist".
                await asyncio.sleep(7)

                # [Dev-Ассистент]: Цикл опроса теперь будет начинаться, когда операция уже точно существует.
                for _ in range(60): # Оставляем цикл на ~2 минуты
                    async with session.get(operation_url, headers=headers) as op_resp:
                        if op_resp.status != 200:
                            error_body = await op_resp.text()
                            logger.error(
                                f"Ошибка при проверке статуса операции YandexArt ({op_resp.status}): {error_body}"
                            )
                            # [Dev-Ассистент]: Если мы все же получаем 404, сообщаем об этом.
                            if op_resp.status == 404:
                                return None, f"Ошибка от Yandex (404): Операция не найдена. Возможно, она была удалена или еще не создана."
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
                    
                    # [Dev-Ассистент]: Пауза между попытками опроса остается 2 секунды.
                    await asyncio.sleep(2)


                return None, "Время ожидания генерации истекло."

        except aiohttp.ClientConnectorError as e:
            logger.error(f"Ошибка соединения с YandexArt: {e}")
            return None, f"Не удалось подключиться к серверам Yandex. Ошибка: {e}"
        except Exception as e:
            logger.error(f"Неизвестная ошибка при работе с YandexArt: {e}", exc_info=True)
            return None, f"Неизвестная ошибка: {e}"