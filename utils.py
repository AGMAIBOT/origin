# utils.py (ФИНАЛЬНАЯ ВЕРСИЯ - 29.06.2025)

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
import constants
import database as db
from constants import TIER_FREE, OUTPUT_FORMAT_TEXT, OUTPUT_FORMAT_TXT, OUTPUT_FORMAT_PDF
import tiktoken
from typing import Dict

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)
logging.getLogger('utils').setLevel(logging.ERROR)

# [Dev-Ассистент]: Это позволит нам легко сравнивать, "выше" или "ниже" тариф пользователя.
TIER_HIERARCHY = {constants.TIER_FREE: 0, constants.TIER_LITE: 1, constants.TIER_PRO: 2}

# --- БЛОК ОБРАБОТКИ ТЕКСТА ---

def markdown_to_html(text: str) -> str:
    """Конвертирует Markdown в поддерживаемый Telegram HTML."""
    # Экранируем спецсимволы, чтобы избежать инъекций
    processed_text = html.escape(text)

    # Порядок важен: от более специфичных маркеров к менее.
    # Сначала многострочный код, чтобы его содержимое не обрабатывалось дальше
    processed_text = re.sub(r'```(.*?)```', r'<pre>\1</pre>', processed_text, flags=re.DOTALL)
    
    # Заголовки (все уровни превращаются в жирный текст)
    processed_text = re.sub(r'^\s*#### (.*?)\s*$', r'<b>\1</b>', processed_text, flags=re.MULTILINE)
    processed_text = re.sub(r'^\s*### (.*?)\s*$', r'<b>\1</b>', processed_text, flags=re.MULTILINE)
    processed_text = re.sub(r'^\s*## (.*?)\s*$', r'<b>\1</b>', processed_text, flags=re.MULTILINE)
    processed_text = re.sub(r'^\s*# (.*?)\s*$', r'<b>\1</b>', processed_text, flags=re.MULTILINE)
    
    # Жирный и курсив
    processed_text = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', processed_text)
    processed_text = re.sub(r'\*(.*?)\*', r'<i>\1</i>', processed_text)
    
    # Однострочный код
    processed_text = re.sub(r'`(.*?)`', r'<code>\1</code>', processed_text)
    
    # "Раз-экранируем" основные сущности обратно (кавычки, амперсанды)
    processed_text = html.unescape(processed_text)

    return processed_text


def strip_html_tags(text: str) -> str:
    """Удаляет HTML-теги из текста для чистого вывода в TXT."""
    return re.sub('<[^<]+?>', '', text)

# [Dev-Ассистент]: НАША НОВАЯ ФУНКЦИЯ
def strip_markdown_for_prompt(text: str) -> str:
    """
    [Dev-Ассистент]: Удаляет основные символы Markdown из строки.
    [Dev-Ассистент]: Используется для "очистки" промптов перед отправкой в API,
    [Dev-Ассистент]: которые не поддерживают форматирование (например, DALL-E).
    """
    # [Dev-Ассистент]: Удаляем символы: *, _, ~, `, ```
    # [Dev-Ассистент]: Это регулярное выражение находит любой из символов в скобках [] и заменяет его на пустую строку.
    processed_text = re.sub(r'[*_~`]', '', text)
    return processed_text


# --- КЛАСС ДЛЯ "УМНОЙ" ГЕНЕРАЦИИ PDF ---

class PDF(FPDF):
    """
    Кастомный класс для создания PDF с поддержкой базового HTML форматирования.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.set_auto_page_break(True, margin=15)
        try:
            # Регистрируем все 4 нужных нам шрифта
            self.add_font('DejaVu', '', 'assets/DejaVuSans.ttf')
            self.add_font('DejaVu', 'B', 'assets/DejaVuSans-Bold.ttf')
            self.add_font('DejaVu', 'I', 'assets/DejaVuSans-Oblique.ttf')
            self.add_font('DejaVuMono', '', 'assets/DejaVuSansMono.ttf') # Моноширинный
            
            self.set_font('DejaVu', '', 11) 
        except RuntimeError as e:
            logger.error(f"КРИТИЧЕСКАЯ ОШИБКА ЗАГРУЗКИ ШРИФТОВ: {e}. Убедитесь, что все 4 файла шрифтов DejaVu лежат в папке /assets. PDF будет создан со стандартным шрифтом, возможны ошибки.")
            self.set_font('Arial', '', 11)

    def write_html(self, html_text: str):
        """Парсит строку с базовыми HTML тегами и форматирует вывод в PDF."""
        # Разбиваем текст на части по тегам, сохраняя сами теги как разделители
        parts = re.split(r'(<b>|</b>|<i>|</i>|<code>|</code>|<pre>|</pre>)', html_text)
        
        for part in parts:
            if not part: continue # Пропускаем пустые строки после split

            if part == '<b>':
                self.set_font(style='B')
            elif part == '</b>':
                self.set_font(style='')
            elif part == '<i>':
                self.set_font(style='I')
            elif part == '</i>':
                self.set_font(style='')
            elif part == '<code>' or part == '<pre>':
                self.set_font('DejaVuMono', size=10) # ИСПОЛЬЗУЕМ БЕЗОПАСНЫЙ ШРИФТ
            elif part == '</code>' or part == '</pre>':
                self.set_font('DejaVu', '', 11) # Возвращаем основной шрифт
            else:
                # Обработка обычного текста и списков
                clean_part = html.unescape(part)
                lines = clean_part.split('\n')
                for line in lines:
                    stripped_line = line.strip()
                    if not stripped_line: continue

                    if stripped_line.startswith('- '):
                        self.set_x(15)
                        self.multi_cell(0, 7, f"• {stripped_line[2:]}")
                    else:
                        self.set_x(10)
                        self.multi_cell(0, 7, stripped_line)


def create_pdf_from_html(html_text: str) -> bytes:
    """Создает PDF-файл из HTML-текста, используя кастомный рендерер PDF."""
    pdf = PDF()
    pdf.add_page()
    pdf.write_html(html_text)
    return pdf.output()


# --- ОСНОВНЫЕ УТИЛИТЫ ---

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
    """Отправляет ответ пользователю в заданном формате (HTML, txt или PDF)."""
    message_to_interact = update.message or (update.callback_query and update.callback_query.message)
    chat_id = message_to_interact.chat_id

    if output_format == OUTPUT_FORMAT_TEXT:
        max_length = 4096
        if len(text) <= max_length:
            await context.bot.send_message(chat_id=chat_id, text=text, reply_markup=reply_markup, parse_mode='HTML')
        else:
            # [Dev-Ассистент]: !!! РЕШЕНИЕ: "УМНЫЕ НОЖНИЦЫ" !!!
            # [Dev-Ассистент]: Вместо простого разделения, мы будем аккуратно
            # [Dev-Ассистент]: резать текст по последнему переносу строки,
            # [Dev-Ассистент]: чтобы не сломать HTML-теги.
            parts = []
            remaining_text = text
            while len(remaining_text) > max_length:
                # Находим точку разреза, не превышая лимит
                cut_at = remaining_text.rfind('\n', 0, max_length)
                # Если перенос строки не найден (очень длинная строка без \n),
                # режем по лимиту, чтобы избежать бесконечного цикла.
                if cut_at == -1:
                    cut_at = max_length
                
                parts.append(remaining_text[:cut_at])
                remaining_text = remaining_text[cut_at:].lstrip() # Удаляем лишние пробелы в начале следующей части

            # Добавляем оставшийся "хвост"
            if remaining_text:
                parts.append(remaining_text)

            for i, part in enumerate(parts):
                # Клавиатуру прикрепляем только к последнему сообщению
                current_reply_markup = reply_markup if i == len(parts) - 1 else None
                if part: # Отправляем, только если часть не пустая
                    await context.bot.send_message(
                        chat_id=chat_id, text=part, reply_markup=current_reply_markup, parse_mode='HTML'
                    )

    elif output_format == OUTPUT_FORMAT_TXT:
        # ... (этот блок без изменений)
        try:
            clean_text = strip_html_tags(text)
            text_bytes = clean_text.encode('utf-8')
            text_file = BytesIO(text_bytes)
            await context.bot.send_document(
                chat_id=chat_id, document=text_file, filename="response.txt", caption="Ваш ответ в формате .txt"
            )
        except Exception as e:
            logger.error(f"Ошибка при создании .txt файла: {e}", exc_info=True)
            await context.bot.send_message(chat_id=chat_id, text="Не удалось сформировать .txt файл.")

    elif output_format == OUTPUT_FORMAT_PDF:
        # ... (этот блок без изменений)
        try:
            loop = asyncio.get_running_loop()
            pdf_bytes = await loop.run_in_executor(None, create_pdf_from_html, text)
            pdf_file = BytesIO(pdf_bytes)
            pdf_file.name = "response.pdf" 
            await context.bot.send_document(
                chat_id=chat_id, document=pdf_file, filename="response.pdf", caption="Ваш ответ в формате .pdf"
            )
        except Exception as e:
            logger.error(f"Ошибка при создании .pdf файла: {e}", exc_info=True)
            await context.bot.send_message(chat_id=chat_id, text="Не удалось сформировать .pdf файл.")

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
async def get_user_ai_provider(user_data: dict) -> str:
    """
    [Dev-Ассистент]: Определяет AI-провайдера для пользователя по четким правилам.
    [Dev-Ассистент]: Приоритет №1: Личный выбор пользователя из его профиля.
    [Dev-Ассистент]: Приоритет №2: Провайдер по умолчанию для его тарифного плана из config.py.
    [Dev-Ассистент]: Приоритет №3: Глобальный "запасной" провайдер, если что-то пошло не так.
    """
    # Приоритет №1: Личный выбор пользователя (например, у Pro-тарифа)
    personal_choice = user_data.get('current_ai_provider')
    if personal_choice:
        logger.debug(f"Используем личный выбор пользователя {user_data['id']}: {personal_choice}")
        return personal_choice

    # Приоритет №2: Настройка по умолчанию из тарифа
    user_tier = await get_actual_user_tier(user_data)
    tier_config = config.SUBSCRIPTION_TIERS.get(user_tier)
    
    if tier_config and tier_config.get('ai_provider'):
        tier_default_provider = tier_config['ai_provider']
        logger.debug(f"Используем провайдера по умолчанию для тарифа '{user_tier}': {tier_default_provider}")
        return tier_default_provider
    
    # Приоритет №3: Абсолютный "спасательный круг"
    logger.warning(
        f"Не удалось определить провайдера для тарифа '{user_tier}'. "
        f"Используется глобальный запасной вариант: {constants.GPT_1}"
    )
    return constants.GPT_1

async def set_user_ai_provider(user_id: int, provider_name: str | None) -> None:
    """
    [Dev-Ассистент]: Устанавливает или сбрасывает выбранный AI-провайдер для пользователя.
    [Dev-Ассистент]: Если provider_name равен None, сбрасывает на NULL в БД.
    """
    await db.db_request("UPDATE users SET current_ai_provider = ? WHERE id = ?", (provider_name, user_id))
    logger.info(f"Для пользователя user_id={user_id} установлен AI-провайдер: {provider_name or 'по умолчанию'}")

def count_gpt_tokens(text: str, model_name: str = "gpt-4") -> int:
    """
    Подсчитывает количество токенов в заданной строке текста для GPT-моделей.
    Использует библиотеку tiktoken.
    :param text: Строка текста для подсчета.
    :param model_name: Имя модели (например, 'gpt-4', 'gpt-3.5-turbo').
                       Влияет на выбор токенайзера. По умолчанию 'gpt-4'.
    :return: Количество токенов.
    """
    try:
        # tiktoken.encoding_for_model может не найти некоторые специфические модели OpenRouter или очень новые/старые.
        # В таком случае, tiktoken рекомендует использовать 'cl100k_base' (используется для GPT-4, GPT-3.5-turbo).
        try:
            encoding = tiktoken.encoding_for_model(model_name)
        except KeyError:
            logger.warning(f"Токенайзер для модели '{model_name}' не найден, используя 'cl100k_base'.")
            encoding = tiktoken.get_encoding("cl100k_base")
            
        return len(encoding.encode(text))
    except Exception as e:
        logger.error(f"Ошибка при подсчете токенов в utils.count_gpt_tokens: {e}", exc_info=True)
        return 0 # Возвращаем 0 в случае ошибки