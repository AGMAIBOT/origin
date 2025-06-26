# utils.py

import logging
from datetime import datetime 
from telegram import ReplyKeyboardMarkup, KeyboardButton, Update
from functools import wraps
from telegram.ext import ContextTypes
import config

# [Dev-Ассистент]: Новые импорты для работы с аудио
from io import BytesIO
from pydub import AudioSegment

import database as db
from constants import TIER_FREE
logger = logging.getLogger(__name__)

def get_main_keyboard() -> ReplyKeyboardMarkup:
    """Возвращает объект ReplyKeyboardMarkup с основными командами в две колонки."""
    keyboard = [
        [KeyboardButton("Персонажи"), KeyboardButton("Выбор AI")],
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
    max_length = 4096
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
    if current_tier != TIER_FREE and expiry_date_str:
        expiry_date = datetime.fromisoformat(expiry_date_str) if isinstance(expiry_date_str, str) else expiry_date_str
        if expiry_date and expiry_date < datetime.now():
            logger.info(f"Подписка для user_id={user_data['id']} истекла. Сбрасываем до 'free'.")
            await db.set_user_tier_to_free(user_data['id'])
            return TIER_FREE
    return current_tier

def require_verification(func):
    """
    Декоратор, который проверяет, верифицирован ли пользователь.
    Если нет - блокирует выполнение функции и просит пройти проверку.
    """
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        if (update.message and update.message.text and update.message.text.startswith('/start')) or \
           (update.message and update.message.entities and any(e.type == 'bot_command' and update.message.text[e.offset:e.offset+e.length] == '/start' for e in update.message.entities)):
            return await func(update, context, *args, **kwargs)
        user_data = await db.get_user_by_telegram_id(update.effective_user.id)
        if user_data and user_data.get('is_verified'):
            return await func(update, context, *args, **kwargs)
        else:
            message = update.message or update.callback_query.message
            await message.reply_text(
                "Для доступа к функциям бота, пожалуйста, пройдите проверку.\n"
                "Нажмите /start"
            )
            return
    return wrapper

def inject_user_data(func):
    """
    Декоратор, который "внедряет" user_data в качестве аргумента в оборачиваемую функцию.
    """
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user_id = await db.add_or_update_user(
            update.effective_user.id,
            update.effective_user.full_name,
            update.effective_user.username
        )
        if not user_id:
            message = update.message or update.callback_query.message
            await message.reply_text("Произошла ошибка с вашим профилем. Попробуйте позже.")
            return
        user_data = await db.get_user_by_id(user_id)
        if not user_data:
            message = update.message or update.callback_query.message
            await message.reply_text("Не удалось загрузить данные вашего профиля.")
            return
        return await func(update, context, user_data=user_data, *args, **kwargs)
    return wrapper

class FileSizeError(Exception):
    """Кастомное исключение для слишком больших файлов."""
    pass

async def get_text_content_from_document(document_file, context: ContextTypes.DEFAULT_TYPE) -> str:
    """
    Универсальная функция для чтения текстового содержимого из файла.
    """
    if document_file.mime_type != 'text/plain' and not document_file.file_name.lower().endswith('.txt'):
        raise ValueError("Неподдерживаемый тип файла. Разрешены только текстовые файлы (.txt).")
    if document_file.file_size and document_file.file_size > config.ABSOLUTE_MAX_FILE_CHARS * 4: 
        raise FileSizeError(f"Файл слишком большой (>{config.ABSOLUTE_MAX_FILE_CHARS * 4} байт).")
    file = await context.bot.get_file(document_file.file_id)
    downloaded_bytes = await file.download_as_bytearray()
    try:
        text_content = downloaded_bytes.decode('utf-8')
    except UnicodeDecodeError:
        text_content = downloaded_bytes.decode('windows-1251', errors='ignore')
    if len(text_content) > config.ABSOLUTE_MAX_FILE_CHARS:
        raise FileSizeError(f"Файл слишком большой ({len(text_content)} символов). Максимум: {config.ABSOLUTE_MAX_FILE_CHARS}.")
    return text_content

# [Dev-Ассистент]: НОВАЯ ФУНКЦИЯ ДЛЯ КОНВЕРТАЦИИ АУДИО
def convert_oga_to_mp3_in_memory(oga_bytearray: bytearray) -> bytes:
    """
    Конвертирует аудио из формата OGG/Opus (от Telegram) в MP3 в оперативной памяти.
    :param oga_bytearray: Аудиофайл в виде байтового массива.
    :return: Аудиофайл в формате MP3 в виде байтов.
    """
    # Создаем файловый объект в памяти из байтового массива
    oga_audio_stream = BytesIO(oga_bytearray)
    
    # Загружаем аудио из потока с помощью pydub
    audio = AudioSegment.from_file(oga_audio_stream, format="ogg")
    
    # Создаем буфер в памяти для сохранения MP3
    mp3_buffer = BytesIO()
    
    # Экспортируем аудио в MP3 в этот буфер
    audio.export(mp3_buffer, format="mp3")
    
    # Возвращаем содержимое буфера в виде байтов
    return mp3_buffer.getvalue()