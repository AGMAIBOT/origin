# ai_clients/base_client.py

from abc import ABC, abstractmethod
from typing import List, Dict, Tuple
from PIL.Image import Image

class BaseAIClient(ABC):
    """
    Абстрактный базовый класс ('контракт') для всех AI клиентов.
    Определяет, какие методы должен реализовывать каждый клиент.
    """

    @abstractmethod
    async def get_text_response(self, chat_history: List[Dict], user_prompt: str) -> Tuple[str, int]:
        """
        Получает текстовый ответ от AI.

        :param chat_history: История диалога в унифицированном формате.
        :param user_prompt: Новый запрос от пользователя.
        :return: Кортеж (текст_ответа: str, потрачено_токенов: int).
        """
        pass

    @abstractmethod
    @abstractmethod
    async def get_image_response(self, chat_history: List[Dict], text_prompt: str, image: Image) -> Tuple[str, int]:
        """
        Получает текстовый ответ от AI на основе ИСТОРИИ, изображения и текста.

        :param chat_history: История диалога в унифицированном формате.
        :param text_prompt: Текстовый запрос к изображению.
        :param image: Объект изображения PIL.Image.
        :return: Кортеж (текст_ответа: str, потрачено_токенов: int).
        """
        pass
    
    @abstractmethod
    def supports_characters(self) -> bool:
        """Возвращает True, если клиент поддерживает кастомные промпты персонажей."""
        pass

    # В будущем здесь можно добавить другие методы, например:
    # @abstractmethod
    # async def generate_image(...) -> Tuple[bytes, int]:
    #     pass