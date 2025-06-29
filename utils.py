import logging
import re
import html
from datetime import datetime 
from telegram import ReplyKeyboardMarkup, KeyboardButton, Update, InlineKeyboardMarkup
from functools import wraps
from telegram.ext import ContextTypes
import config
from io import BytesIO
from pydub import AudioSegment
from fpdf import FPDF
import asyncio

import database as db
from constants import TIER_FREE, OUTPUT_FORMAT_TEXT, OUTPUT_FORMAT_TXT, OUTPUT_FORMAT_PDF
logger = logging.getLogger(__name__)

# --- [Dev-Ассистент]: НАЧАЛО НОВОГО БЛОКА С КОНВЕРТЕРОМ И ГЕНЕРАТОРОМ PDF ---

def markdown_to_html(text: str) -> str:
    """
    Конвертирует базовый Markdown от LLM в безопасный и ПОДДЕРЖИВАЕМЫЙ Telegram HTML.
    """
    text = html.escape(text)

    # [Dev-Ассистент]: ПОРЯДОК ВАЖЕН! Сначала обрабатываем более длинные маркеры.
    
    # 1. Многострочный код ```код``` -> <pre>код</pre>
    text = re.sub(r'```(.*?)```', r'<pre>\1</pre>', text, flags=re.DOTALL)
    
    # 2. Жирный текст **жирный** -> <b>жирный</b>
    text = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', text)

    # 3. Курсив *курсив* -> <i>курсив</i> (ИСПРАВЛЕННАЯ ВЕРСИЯ)
    text = re.sub(r'\*(.*?)\*', r'<i>\1</i>', text)
    
    # 4. Однострочный код `код` -> <code>код</code>
    text = re.sub(r'`(.*?)`', r'<code>\1</code>', text)

    # 5. Заголовки ### Заголовок -> <b>Заголовок</b>
    text = re.sub(r'^\s*### (.*?)\s*$', r'<b>\1</b>', text, flags=re.MULTILINE)

    return text

def clean_text_for_pdf(text: str) -> str:
    """
    Убирает любую Markdown разметку для чистого вывода в PDF.
    """
    # Удаляем **жирный** -> жирный
    text = re.sub(r'\*\*(.*?)\*\*', r'\1', text)
    # Удаляем *курсив* -> курсив
    text = re.sub(r'\*(.*?)\*', r'\1', text)
    # Удаляем ```код``` -> код
    text = re.sub(r'```(.*?)```', r'\1', text, flags=re.DOTALL)
    # Удаляем `код` -> код
    text = re.sub(r'`(.*?)`', r'\1', text)
    # Удаляем ### Заголовок -> Заголовок
    text = re.sub(r'### (.*?)\n', r'\1\n', text)

    return text

def create_pdf_from_text(text: str) -> bytes:
    """
    Создает PDF-файл из текста в оперативной памяти с поддержкой кириллицы.
    """
    pdf = FPDF()
    try:
        pdf.add_font('DejaVu', '', 'assets/DejaVuSans.ttf')
        pdf.set_font('DejaVu', size=10)
    except RuntimeError:
        logger.error("Ошибка загрузки шрифта 'assets/DejaVuSans.ttf'. PDF будет создан без кириллицы.")
        pdf.set_font('Arial', size=10)
    
    pdf.add_page()
    # [Dev-Ассистент]: Используем очищенный текст для PDF
    clean_text = clean_text_for_pdf(text)
    pdf.multi_cell(w=0, h=7, text=clean_text)
    
    return pdf.output()

# --- [Dev-Ассистент]: КОНЕЦ НОВОГО БЛОКА ---


def get_main_keyboard() -> ReplyKeyboardMarkup:
    # ... (без изменений)
    keyboard = [[KeyboardButton("Персонажи"), KeyboardButton("Выбор AI")], [KeyboardButton("⚙️ Профиль"), KeyboardButton("🤖 AGM, научи меня!")]]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)

async def delete_message_callback(context: ContextTypes.DEFAULT_TYPE) -> None:
    # ... (без изменений)
    job_data = context.job.data
    try:
        await context.bot.delete_message(chat_id=job_data['chat_id'], message_id=job_data['message_id'])
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
    Отправляет ответ пользователю в заданном формате (HTML, txt или PDF).
    """
    message_to_interact = update.message or (update.callback_query and update.callback_query.message)
    chat_id = message_to_interact.chat_id

    # Сценарий 1: Отправка текстом в чат (теперь всегда HTML)
    if output_format == OUTPUT_FORMAT_TEXT:
        max_length = 4096
        # [Dev-Ассистент]: Мы предполагаем, что текст УЖЕ в формате HTML
        if len(text) <= max_length:
            # [Dev-Ассистент]: ДОБАВЛЯЕМ ЛОГ ПРЯМО ПЕРЕД ОТПРАВКОЙ
            logger.info(f"[ОТЛАДКА] Попытка отправить HTML: {text}")
            await context.bot.send_message(chat_id=chat_id, text=text, reply_markup=reply_markup, parse_mode='HTML')
        else:
            # [Dev-Ассистент]: Логику для длинных сообщений пока упростим для отладки,
            # [Dev-Ассистент]: чтобы проблема точно проявилась на первом фрагменте.
            part = text[:max_length]
            logger.info(f"[ОТЛАДКА] Попытка отправить ПЕРВУЮ ЧАСТЬ HTML: {part}")
            await context.bot.send_message(chat_id=chat_id, text=part, reply_markup=None, parse_mode='HTML')
            
            # Отправляем остальное без форматирования, чтобы не спамить в случае ошибки
            if len(text) > max_length:
                 await context.bot.send_message(chat_id=chat_id, text="[...остальная часть ответа опущена для отладки...]")

    # Сценарий 2: Отправка файлом .txt
    elif output_format == OUTPUT_FORMAT_TXT:
        try:
            # [Dev-Ассистент]: Очищаем текст от разметки для чистого .txt
            clean_text = clean_text_for_pdf(text)
            text_bytes = clean_text.encode('utf-8')
            text_file = BytesIO(text_bytes)
            await context.bot.send_document(
                chat_id=chat_id, document=text_file, filename="response.txt", caption="Ваш ответ в формате .txt"
            )
        except Exception as e:
            logger.error(f"Ошибка при создании .txt файла: {e}", exc_info=True)
            await context.bot.send_message(chat_id=chat_id, text="Не удалось сформировать .txt файл.")

    # Сценарий 3: Отправка файлом .pdf
    elif output_format == OUTPUT_FORMAT_PDF:
        try:
            loop = asyncio.get_running_loop()
            # [Dev-Ассистент]: Передаем "сырой" текст, create_pdf_from_text сам его очистит
            pdf_bytes = await loop.run_in_executor(None, create_pdf_from_text, text)
            
            pdf_file = BytesIO(pdf_bytes)
            pdf_file.name = "response.pdf" 
            await context.bot.send_document(
                chat_id=chat_id, document=pdf_file, filename="response.pdf", caption="Ваш ответ в формате .pdf"
            )
        except Exception as e:
            logger.error(f"Ошибка при создании .pdf файла: {e}", exc_info=True)
            await context.bot.send_message(chat_id=chat_id, text="Не удалось сформировать .pdf файл.")  

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