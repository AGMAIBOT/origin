# utils.py (ПОЛНАЯ ВЕРСИЯ С ГЕНЕРАЦИЕЙ PDF)

import logging
from datetime import datetime 
from telegram import ReplyKeyboardMarkup, KeyboardButton, Update, InlineKeyboardMarkup
from functools import wraps
from telegram.ext import ContextTypes
import config
from io import BytesIO

# [Dev-Ассистент]: Новые импорты для PDF и аудио
from pydub import AudioSegment
from fpdf import FPDF
import asyncio

import database as db
from constants import TIER_FREE, OUTPUT_FORMAT_TEXT, OUTPUT_FORMAT_TXT, OUTPUT_FORMAT_PDF
logger = logging.getLogger(__name__)


# --- [Dev-Ассистент]: НАЧАЛО НОВОГО БЛОКА С ГЕНЕРАТОРОМ PDF ---

def create_pdf_from_text(text: str) -> bytes:
    """
    Создает PDF-файл из текста в оперативной памяти с поддержкой кириллицы.
    Эта функция является СИНХРОННОЙ и должна вызываться через run_in_executor.
    
    :param text: Текст для добавления в PDF.
    :return: PDF-файл в виде байтов.
    """
    pdf = FPDF()
    
    # 1. Добавляем шрифт с поддержкой Unicode (для кириллицы)
    #    Предполагается, что файл DejaVuSans.ttf лежит в папке assets
    try:
        # Указываем путь к шрифту относительно корня проекта
        pdf.add_font('DejaVu', '', 'assets/DejaVuSans.ttf')
    except RuntimeError:
        # Эта ошибка может возникнуть, если FPDF не может найти или обработать файл шрифта
        logger.error(
            "Ошибка при загрузке шрифта 'assets/DejaVuSans.ttf'. "
            "Убедитесь, что файл существует и не поврежден. "
            "PDF будет создан без поддержки кириллицы."
        )
        # В качестве запасного варианта, используем стандартный шрифт
        pdf.set_font('Arial', size=12)
    else:
        # 2. Устанавливаем добавленный шрифт, только если он успешно загрузился
        pdf.set_font('DejaVu', size=7)
    
    # 3. Добавляем страницу
    pdf.add_page()
    
    # 4. Используем multi_cell для автоматического переноса текста
    #    w=0 означает, что ячейка будет занимать всю ширину от левого до правого поля.
    #    h=10 - высота строки
    pdf.multi_cell(w=0, h=5, text=text)
    
    # 5. Возвращаем результат в виде байтов
    return pdf.output()

# --- [Dev-Ассистент]: КОНЕЦ НОВОГО БЛОКА ---


def get_main_keyboard() -> ReplyKeyboardMarkup:
    """Возвращает основную клавиатуру с кнопками меню."""
    keyboard = [
        [KeyboardButton("Персонажи"), KeyboardButton("Выбор AI")],
        [KeyboardButton("⚙️ Профиль"), KeyboardButton("🤖 AGM, научи меня!")]
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


async def send_long_message(
    update: Update, 
    context: ContextTypes.DEFAULT_TYPE,
    text: str, 
    reply_markup: InlineKeyboardMarkup = None,
    output_format: str = OUTPUT_FORMAT_TEXT
):
    """
    Отправляет ответ пользователю в заданном формате (текст, txt или PDF).
    """
    message_to_interact = update.message or (update.callback_query and update.callback_query.message)
    chat_id = message_to_interact.chat_id

    # --- Маршрутизация по формату вывода ---
    
    # Сценарий 1: Отправка текстом в чат
    if output_format == OUTPUT_FORMAT_TEXT:
        max_length = 4096
        if len(text) <= max_length:
            await context.bot.send_message(chat_id=chat_id, text=text, reply_markup=reply_markup)
        else:
            parts = [text[i:i + max_length] for i in range(0, len(text), max_length)]
            for i, part in enumerate(parts):
                current_reply_markup = reply_markup if i == len(parts) - 1 else None
                await context.bot.send_message(chat_id=chat_id, text=part, reply_markup=current_reply_markup)

    # Сценарий 2: Отправка файлом .txt
    elif output_format == OUTPUT_FORMAT_TXT:
        try:
            text_bytes = text.encode('utf-8')
            text_file = BytesIO(text_bytes)
            await context.bot.send_document(
                chat_id=chat_id,
                document=text_file,
                filename="response.txt",
                caption="Ваш ответ в формате .txt"
            )
        except Exception as e:
            logger.error(f"Ошибка при создании .txt файла: {e}", exc_info=True)
            await context.bot.send_message(chat_id=chat_id, text="Не удалось сформировать .txt файл. Вот ответ текстом:")
            await send_long_message(update, context, text, reply_markup, OUTPUT_FORMAT_TEXT)

    # --- [Dev-Ассистент]: НАЧАЛО ИЗМЕНЕНИЙ В БЛОКЕ PDF ---
    # Сценарий 3: Отправка файлом .pdf
    elif output_format == OUTPUT_FORMAT_PDF:
        try:
            # Запускаем синхронную ресурсоемкую задачу в отдельном потоке,
            # чтобы не блокировать бота.
            loop = asyncio.get_running_loop()
            pdf_bytes = await loop.run_in_executor(None, create_pdf_from_text, text)
            
            pdf_file = BytesIO(pdf_bytes)
            # [Dev-Ассистент]: Важно! Telegram требует, чтобы у файлового объекта в памяти было имя.
            pdf_file.name = "response.pdf" 
            
            await context.bot.send_document(
                chat_id=chat_id,
                document=pdf_file,
                filename="response.pdf", # Имя файла, которое увидит пользователь
                caption="Ваш ответ в формате .pdf"
            )
        except Exception as e:
            logger.error(f"Ошибка при создании .pdf файла: {e}", exc_info=True)
            await context.bot.send_message(chat_id=chat_id, text="Не удалось сформировать .pdf файл. Вот ответ текстом:")
            # В случае ошибки - отправляем обычным текстом
            await send_long_message(update, context, text, reply_markup, OUTPUT_FORMAT_TEXT)
    # --- [Dev-Ассистент]: КОНЕЦ ИЗМЕНЕНИЙ В БЛОКЕ PDF ---
            

async def get_actual_user_tier(user_data: dict) -> str:
    """
    Централизованно проверяет срок действия подписки, при необходимости обновляет
    ее в БД и возвращает актуальный тариф.
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
    """
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        if update.message and update.message.text and update.message.text.startswith('/start'):
            return await func(update, context, *args, **kwargs)

        user_data = await db.get_user_by_telegram_id(update.effective_user.id)

        if user_data and user_data.get('is_verified'):
            return await func(update, context, *args, **kwargs)
        else:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="Для доступа к функциям бота, пожалуйста, пройдите проверку.\nНажмите /start"
            )
            if update.callback_query:
                await update.callback_query.answer()
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


def convert_oga_to_mp3_in_memory(oga_bytearray: bytearray) -> bytes:
    """
    Конвертирует аудио из формата OGG/Opus (от Telegram) в MP3 в оперативной памяти.
    """
    oga_audio_stream = BytesIO(oga_bytearray)
    audio = AudioSegment.from_file(oga_audio_stream, format="ogg")
    mp3_buffer = BytesIO()
    audio.export(mp3_buffer, format="mp3")
    return mp3_buffer.getvalue()