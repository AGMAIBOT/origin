import logging
from datetime import datetime 
from telegram import ReplyKeyboardMarkup, KeyboardButton, Update
from functools import wraps
from telegram.ext import ContextTypes
import config

# Импортируем нужные модули для новой функции
import database as db
from constants import TIER_FREE
logger = logging.getLogger(__name__)

def get_main_keyboard() -> ReplyKeyboardMarkup:
    """Возвращает объект ReplyKeyboardMarkup с основными командами в две колонки."""
    keyboard = [
        # Первый ряд кнопок
        [KeyboardButton("Персонажи"), KeyboardButton("Выбор AI")],
        # Второй ряд кнопок
        [KeyboardButton("Профиль"), KeyboardButton("Настройки")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)

async def delete_message_callback(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Удаляет сообщение по расписанию. Получает chat_id и message_id из job.data."""
    job_data = context.job.data
    try:
        await context.bot.delete_message(chat_id=job_data['chat_id'], message_id=job_data['message_id'])
        logger.info(f"Сообщение {job_data['message_id']} в чате {job_data['chat_id']} удалено по расписанию.")
    except Exception as e:
        logger.warning(f"Не удалось удалить сообщение {job_data['message_id']} в чате {job_data['chat_id']}: {e}")

async def send_long_message(update: Update, text: str):
    """Разбивает длинное сообщение на части и отправляет их по отдельности."""
    max_length = 4096  # Максимальная длина сообщения в Telegram
    if len(text) <= max_length:
        await update.message.reply_text(text)
    else:
        parts = [text[i:i + max_length] for i in range(0, len(text), max_length)]
        for part in parts:
            await update.message.reply_text(part)
async def get_actual_user_tier(user_data: dict) -> str:
    """
    Централизованно проверяет срок действия подписки, при необходимости обновляет
    ее в БД и возвращает актуальный тариф. Это единый источник истины.
    """
    current_tier = user_data.get('subscription_tier', TIER_FREE)
    expiry_date_str = user_data.get('subscription_expiry_date')
    
    # Проверяем только если это платный тариф и есть дата истечения
    if current_tier != TIER_FREE and expiry_date_str:
        # Преобразуем строку в объект datetime, если это необходимо
        expiry_date = datetime.fromisoformat(expiry_date_str) if isinstance(expiry_date_str, str) else expiry_date_str
        
        if expiry_date and expiry_date < datetime.now():
            logger.info(f"Подписка для user_id={user_data['id']} истекла. Сбрасываем до 'free'.")
            # Обновляем данные в БД
            await db.set_user_tier_to_free(user_data['id'])
            # Возвращаем новый, актуальный тариф
            return TIER_FREE
    
    # Если подписка не истекла или бесплатная, возвращаем текущий тариф
    return current_tier

def require_verification(func):
    """
    Декоратор, который проверяет, верифицирован ли пользователь.
    Если нет - блокирует выполнение функции и просит пройти проверку.
    """
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        # /start - единственная команда, доступная неавторизованным пользователям.
        # Мы проверяем и текст, и объект команды для надежности.
        if (update.message and update.message.text and update.message.text.startswith('/start')) or \
           (update.message and update.message.entities and any(e.type == 'bot_command' and update.message.text[e.offset:e.offset+e.length] == '/start' for e in update.message.entities)):
            return await func(update, context, *args, **kwargs)

        user_data = await db.get_user_by_telegram_id(update.effective_user.id)

        if user_data and user_data.get('is_verified'):
            return await func(update, context, *args, **kwargs)
        else:
            # Используем message из update, если он есть, иначе из query
            message = update.message or update.callback_query.message
            await message.reply_text(
                "Для доступа к функциям бота, пожалуйста, пройдите проверку.\n"
                "Нажмите /start"
            )
            return
    return wrapper
class FileSizeError(Exception):
    """Кастомное исключение для слишком больших файлов."""
    pass

async def get_text_content_from_document(document_file, context: ContextTypes.DEFAULT_TYPE) -> str:
    """
    Универсальная функция для чтения текстового содержимого из файла.
    Проверяет тип, размер и декодирует содержимое.
    Теперь находится в utils, чтобы быть доступной для всех обработчиков.
    """
    if document_file.mime_type != 'text/plain' and not document_file.file_name.lower().endswith('.txt'):
        raise ValueError("Неподдерживаемый тип файла. Разрешены только текстовые файлы (.txt).")
    
    # Проверяем размер файла в байтах (приблизительная проверка)
    if document_file.file_size and document_file.file_size > config.ABSOLUTE_MAX_FILE_CHARS * 4: 
        raise FileSizeError(f"Файл слишком большой (>{config.ABSOLUTE_MAX_FILE_CHARS * 4} байт).")
    
    file = await context.bot.get_file(document_file.file_id)
    downloaded_bytes = await file.download_as_bytearray()
    
    try:
        text_content = downloaded_bytes.decode('utf-8')
    except UnicodeDecodeError:
        # Если UTF-8 не сработал, пробуем популярную для Windows кодировку
        text_content = downloaded_bytes.decode('windows-1251', errors='ignore')

    # Финальная, точная проверка по количеству символов
    if len(text_content) > config.ABSOLUTE_MAX_FILE_CHARS:
        raise FileSizeError(f"Файл слишком большой ({len(text_content)} символов). Максимум: {config.ABSOLUTE_MAX_FILE_CHARS}.")
    
    return text_content