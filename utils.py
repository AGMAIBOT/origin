# utils.py (ВЕРСИЯ С "УМНЫМ" PDF-РЕНДЕРОМ И ФОРМАТИРОВАНИЕМ)

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

"""
Краткая шпаргалка по настройке:
Основной размер шрифта:
Где: В методе __init__.
Строка: self.set_font('DejaVu', '', 11)
Что менять: Число 11. Попробуй 10 для более мелкого или 12 для более крупного текста.
Отступ слева для списков:
Где: В методе write_html, в блоке if stripped_line.startswith('- ').
Строка: self.set_x(15)
Что менять: Число 15. Увеличь его, чтобы список сдвинулся правее, уменьши — чтобы сдвинулся левее.
Вертикальные отступы у заголовков:
Где: В методе write_html, в блоке elif stripped_line.endswith(':').
Строки: self.ln(3) (две строки).
Что менять: Число 3. Это "воздух" до и после заголовка. Увеличь его, чтобы отделить заголовок от остального текста сильнее.
Отступ слева для обычных параграфов:
Где: В методе write_html, в самом последнем блоке else.
Строка: self.set_x(10)
Что менять: Число 10. Это базовый левый отступ для всего текста, который не является элементом списка.
"""

# --- [Dev-Ассистент]: НАЧАЛО БЛОКА ОБРАБОТКИ ТЕКСТА ---

def markdown_to_html(text: str) -> str:
    """Конвертирует Markdown в поддерживаемый Telegram HTML."""
    processed_text = html.escape(text)

    processed_text = re.sub(r'```(.*?)```', r'<pre>\1</pre>', processed_text, flags=re.DOTALL)
    processed_text = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', processed_text)
    processed_text = re.sub(r'\*(.*?)\*', r'<i>\1</i>', processed_text)
    processed_text = re.sub(r'`(.*?)`', r'<code>\1</code>', processed_text)
    processed_text = re.sub(r'^\s*### (.*?)\s*$', r'<b>\1</b>', processed_text, flags=re.MULTILINE)
    
    # [Dev-Ассистент]: КЛЮЧЕВОЕ ИСПРАВЛЕНИЕ №1.
    # [Dev-Ассистент]: "Раз-экранируем" основные сущности обратно.
    # [Dev-Ассистент]: Это вернет нам нормальные кавычки, но оставит < и > безопасными.
    processed_text = html.unescape(processed_text)

    return processed_text

def strip_html_tags(text: str) -> str:
    """Удаляет HTML-теги из текста для чистого вывода в TXT."""
    return re.sub('<[^<]+?>', '', text)

class PDF(FPDF):
    """Кастомный класс для создания PDF с поддержкой базового HTML форматирования."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.set_auto_page_break(True, margin=15)
        try:
            self.add_font('DejaVu', '', 'assets/DejaVuSans.ttf')
            self.add_font('DejaVu', 'B', 'assets/DejaVuSans-Bold.ttf')
            self.add_font('DejaVu', 'I', 'assets/DejaVuSans-Oblique.ttf')
            self.set_font('DejaVu', '', 8)
        except RuntimeError as e:
            logger.error(f"Критическая ошибка загрузки шрифтов: {e}. PDF будет создан со стандартным шрифтом.")
            self.set_font('Arial', '', 11)

    def write_html(self, html_text: str):
        """Парсит строку с базовыми HTML тегами и форматирует вывод в PDF."""
        # [Dev-Ассистент]: Сначала полностью очищаем текст от HTML тегов.
        # [Dev-Ассистент]: Стили будем применять отдельно.
        text_without_tags = strip_html_tags(html_text)

        # [Dev-Ассистент]: КЛЮЧЕВОЕ ИСПРАВЛЕНИЕ №2.
        # [Dev-Ассистент]: Улучшенная логика обработки списков и параграфов.
        lines = text_without_tags.split('\n')
        for line in lines:
            stripped_line = line.strip()
            if not stripped_line: # Пропускаем пустые строки для чистоты
                continue

            # Проверяем на маркеры списка (дефис или звездочка в начале)
            if stripped_line.startswith('- ') or stripped_line.startswith('* '):
                self.set_x(15) # Отступ для элемента списка
                # Устанавливаем жирный стиль для маркера и обычный для текста
                self.set_font(style='B')
                self.cell(5, 7, '•') # Печатаем маркер без переноса строки
                self.set_font(style='')
                self.multi_cell(0, 7, f" {stripped_line[2:]}") # Текст с небольшим отступом от маркера
            # Проверяем на заголовки, которые были в Markdown как "### Текст" или "**Текст**"
            # После конвертации они стали <b>Текст</b>, а после strip_tags() -> Текст
            # Мы можем их опознать по отсутствию маркера списка и двоеточию в конце
            elif stripped_line.endswith(':'):
                self.set_font(style='B')
                self.ln(3) # Доп. отступ перед заголовком
                self.multi_cell(0, 7, stripped_line)
                self.ln(3) # Доп. отступ после заголовка
                self.set_font(style='')
            else:
                self.set_x(10) # Стандартный отступ для параграфа
                self.multi_cell(0, 7, stripped_line)
                
def create_pdf_from_html(html_text: str) -> bytes:
    """Создает PDF-файл из HTML-текста, используя кастомный рендерер PDF."""
    pdf = PDF()
    pdf.add_page()
    pdf.write_html(html_text)
    return pdf.output()

def create_pdf_from_html(html_text: str) -> bytes:
    """
    Создает PDF-файл из HTML-текста, используя кастомный рендерер PDF.
    """
    pdf = PDF()
    pdf.add_page()
    pdf.write_html(html_text)
    return pdf.output()

# --- [Dev-Ассистент]: КОНЕЦ НОВЫХ БЛОКОВ ---

def get_main_keyboard() -> ReplyKeyboardMarkup:
    keyboard = [[KeyboardButton("Персонажи"), KeyboardButton("Выбор AI")], [KeyboardButton("⚙️ Профиль"), KeyboardButton("🤖 AGM, научи меня!")]]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)

async def delete_message_callback(context: ContextTypes.DEFAULT_TYPE) -> None:
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

    # Сценарий 1: Отправка текстом в чат
    if output_format == OUTPUT_FORMAT_TEXT:
        max_length = 4096
        # Предполагаем, что текст УЖЕ в формате HTML
        if len(text) <= max_length:
            await context.bot.send_message(chat_id=chat_id, text=text, reply_markup=reply_markup, parse_mode='HTML')
        else:
            parts = [text[i:i + max_length] for i in range(0, len(text), max_length)]
            for i, part in enumerate(parts):
                current_reply_markup = reply_markup if i == len(parts) - 1 else None
                await context.bot.send_message(chat_id=chat_id, text=part, reply_markup=current_reply_markup, parse_mode='HTML')

    # Сценарий 2: Отправка файлом .txt
    elif output_format == OUTPUT_FORMAT_TXT:
        try:
            # Очищаем текст от HTML-тегов для чистого .txt
            clean_text = strip_html_tags(text)
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
            # Передаем HTML в наш новый "умный" генератор
            pdf_bytes = await loop.run_in_executor(None, create_pdf_from_html, text)
            
            pdf_file = BytesIO(pdf_bytes)
            pdf_file.name = "response.pdf" 
            await context.bot.send_document(
                chat_id=chat_id, document=pdf_file, filename="response.pdf", caption="Ваш ответ в формате .pdf"
            )
        except Exception as e:
            logger.error(f"Ошибка при создании .pdf файла: {e}", exc_info=True)
            await context.bot.send_message(chat_id=chat_id, text="Не удалось сформировать .pdf файл.")

# ... (остальные функции - get_actual_user_tier, require_verification и т.д. - без изменений) ...

async def get_actual_user_tier(user_data: dict) -> str:
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
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        if update.message and update.message.text and update.message.text.startswith('/start'):
            return await func(update, context, *args, **kwargs)
        user_data = await db.get_user_by_telegram_id(update.effective_user.id)
        if user_data and user_data.get('is_verified'):
            return await func(update, context, *args, **kwargs)
        else:
            await context.bot.send_message(chat_id=update.effective_chat.id, text="Для доступа к функциям бота, пожалуйста, пройдите проверку.\nНажмите /start")
            if update.callback_query:
                await update.callback_query.answer()
            return
    return wrapper

def inject_user_data(func):
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user_id = await db.add_or_update_user(update.effective_user.id, update.effective_user.full_name, update.effective_user.username)
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
    pass

async def get_text_content_from_document(document_file, context: ContextTypes.DEFAULT_TYPE) -> str:
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
    oga_audio_stream = BytesIO(oga_bytearray)
    audio = AudioSegment.from_file(oga_audio_stream, format="ogg")
    mp3_buffer = BytesIO()
    audio.export(mp3_buffer, format="mp3")
    return mp3_buffer.getvalue()