# ai_clients/yandexart_client.py
# [Dev-Ассистент]: ВЕРСИЯ С УЛУЧШЕННОЙ, НАДЕЖНОЙ ОБРАБОТКОЙ ОШИБОК И ВЫБОРОМ РАЗРЕШЕНИЯ

import os
import logging
import asyncio
import time
import json
import base64
from typing import Tuple, Dict
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

    # [Dev-Ассистент]: Добавляем параметр `size`
    async def generate_image(self, prompt: str, size: str = "1:1") -> Tuple[bytes | None, str | None]:
        headers = {
            "Authorization": f"Api-Key {self._api_key}",
            "Content-Type": "application/json"
        }
        
        # [Dev-Ассистент]: Логика определения aspectRatio на основе параметра size
        aspect_ratio_map: Dict[str, Dict[str, str]] = {
            "1024x1024": {"widthRatio": "1", "heightRatio": "1"},
            "1024x1792": {"widthRatio": "9", "heightRatio": "16"}, # 9:16
            "1792x1024": {"widthRatio": "16", "heightRatio": "9"}, # 16:9
        }
        
        # [Dev-Ассистент]: Получаем выбранное соотношение или дефолтное 1:1
        selected_aspect_ratio = aspect_ratio_map.get(size, aspect_ratio_map["1024x1024"])

        payload = {
            "modelUri": f"art://{self._folder_id}/yandex-art/latest",
            "messages": [{"text": prompt, "weight": "1"}],
            "generationOptions": {
                "seed": int(time.time()),
                "aspectRatio": {
                    "widthRatio": selected_aspect_ratio["widthRatio"],  # [Dev-Ассистент]: Динамическое значение
                    "heightRatio": selected_aspect_ratio["heightRatio"] # [Dev-Ассистент]: Динамическое значение
                }
            }
        }

        try:
            async with aiohttp.ClientSession() as session:
                # --- ЭТАП 1: ЗАПУСК ГЕНЕРАЦИИ ---
                logger.info(f"Отправка запроса на генерацию в YandexArt (размер: {size})...") # [Dev-Ассистент]: Улучшенный лог
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

                # [Dev-Ассистент]: Исправление: Увеличиваем начальную задержку.
                await asyncio.sleep(7) 

                for _ in range(60): # Оставляем цикл на ~2 минуты
                    operation_url = OPERATION_API_URL_TEMPLATE.format(operation_id) # [Dev-Ассистент]: Убедимся, что url каждый раз генерируется
                    async with session.get(operation_url, headers=headers) as op_resp:
                        if op_resp.status != 200:
                            error_body = await op_resp.text()
                            logger.error(
                                f"Ошибка при проверке статуса операции YandexArt ({op_resp.status}): {error_body}"
                            )
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
                    
                    await asyncio.sleep(2)

                return None, "Время ожидания генерации истекло."

        except aiohttp.ClientConnectorError as e:
            logger.error(f"Ошибка соединения с YandexArt: {e}")
            return None, f"Не удалось подключиться к серверам Yandex. Ошибка: {e}"
        except Exception as e:
            logger.error(f"Неизвестная ошибка при работе с YandexArt: {e}", exc_info=True)
            return None, f"Неизвестная ошибка: {e}"