# main.py

import os
import logging
from dotenv import load_dotenv
from typing import List

# Настройка логирования
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)


def parse_admin_ids(ids_string: str) -> List[int]:
    admin_ids = []
    for admin_id_str in ids_string.split(','):
        cleaned_id_str = admin_id_str.strip()
        if not cleaned_id_str:
            continue
        try:
            admin_ids.append(int(cleaned_id_str))
        except ValueError:
            logger.warning(f"Не удалось преобразовать ID администратора '{cleaned_id_str}' в число. Значение проигнорировано.")
    return admin_ids

# Загружаем переменные из .env файла
load_dotenv()

loaded_gemini_key = os.getenv('GEMINI_API_KEY')
print(f"--- DEBUG: Загружен ключ Gemini: {loaded_gemini_key} ---")

logger.info("Проверка API ключей...")
logger.info(f"Ключ Gemini: {'Найден' if os.getenv('GEMINI_API_KEY') else 'НЕ НАЙДЕН'}")
logger.info(f"Ключ OpenAI: {'Найден' if os.getenv('OPENAI_API_KEY') else 'НЕ НАЙДЕН'}")
logger.info(f"Ключ DeepSeek: {'Найден' if os.getenv('DEEPSEEK_API_KEY') else 'НЕ НАЙДЕН'}")
logger.info(f"Ключ OpenRouter: {'Найден' if os.getenv('OPENROUTER_API_KEY') else 'НЕ НАЙДЕН'}")

admin_ids_from_env = os.getenv("ADMIN_IDS", "")
ADMIN_IDS = parse_admin_ids(admin_ids_from_env)

if not ADMIN_IDS:
    logger.warning("Переменная ADMIN_IDS не задана или не содержит корректных ID. Функции администратора будут недоступны.")
else:
    logger.info(f"Загружены ID администраторов: {ADMIN_IDS}")

from io import BytesIO
from PIL import Image
from telegram import Update, BotCommand
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
from telegram.helpers import escape_markdown
from telegram.constants import ChatAction
from google.api_core.exceptions import ResourceExhausted

import database as db
import config
from constants import *
from characters import DEFAULT_CHARACTER_NAME, ALL_PROMPTS
from handlers import character_menus, characters_handler, profile_handler, captcha_handler, ai_selection_handler

# <<< ИЗМЕНЕНИЕ: Добавили наш новый декоратор в импорты >>>
from utils import get_main_keyboard, send_long_message, get_actual_user_tier, require_verification, get_text_content_from_document, FileSizeError, inject_user_data
from ai_clients.factory import get_ai_client_with_caps

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

# <<< УДАЛЕНИЕ: Эта функция больше не нужна, т.к. ее логика переехала в декоратор >>>
# async def get_user_db_id(update: Update): return await db.add_or_update_user(update.effective_user.id, update.effective_user.full_name, update.effective_user.username)

# <<< ИЗМЕНЕНИЕ: Полностью переписана функция для реализации "Варианта 3" >>>
async def process_ai_request(update: Update, context: ContextTypes.DEFAULT_TYPE, user_data: dict, user_content: str, is_photo: bool = False, image_obj: Image = None, is_document: bool = False, document_char_count: int = 0):
    
    # --- ЕДИНАЯ ЛОГИКА ПОЛУЧЕНИЯ ДАННЫХ ---
    ai_provider = user_data.get('current_ai_provider') or GEMINI_STANDARD
    user_id = user_data['id']
    char_name = user_data.get('current_character_name', DEFAULT_CHARACTER_NAME)
    
    # Системный промпт определяется одинаково для всех AI
    custom_char = await db.get_custom_character_by_name(user_id, char_name)
    system_instruction = custom_char['prompt'] if custom_char else ALL_PROMPTS.get(char_name, "Ты — полезный ассистент.")
        
    # --- ЕДИНАЯ ЛОГИКА СОЗДАНИЯ КЛИЕНТА И ПРОВЕРКИ ВОЗМОЖНОСТЕЙ ---
    try:
        caps = get_ai_client_with_caps(ai_provider, system_instruction)
        ai_client = caps.client
    except ValueError as e:
        logger.error(f"Ошибка создания AI клиента: {e}")
        await update.message.reply_text(f"Ошибка конфигурации: {e}")
        return

    # Проверки возможностей (vision, файлы)
    if is_photo and not caps.supports_vision:
        await update.message.reply_text(f"К сожалению, выбранная модель AI не умеет обрабатывать изображения. Пожалуйста, переключитесь на модель с поддержкой vision.")
        return
        
    if is_document:
        if caps.file_char_limit == 0:
            await update.message.reply_text(f"Обработка файлов для выбранной модели AI не поддерживается.")
            return
        if document_char_count > caps.file_char_limit:
            await update.message.reply_text(f"Файл слишком большой для этой модели. Максимум: {caps.file_char_limit} символов, в вашем файле: {document_char_count}.")
            return

    # --- ЕДИНАЯ ЛОГИКА РАБОТЫ С ИСТОРИЕЙ И ЗАПРОСОМ К AI ---
    history_len = await db.get_history_length(user_id, char_name)
    if history_len > config.HISTORY_LIMIT_TRIGGER:
        await db.trim_chat_history(user_id, char_name, config.HISTORY_TRIM_TO)

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
    try:
        chat_history = await db.get_chat_history(user_id, char_name, limit=config.DEFAULT_HISTORY_LIMIT)
        
        if is_photo and image_obj:
            response_text, _ = await ai_client.get_image_response(user_content, image_obj)
            db_user_content = f"[Изображение] {user_content}"
        else:
            response_text, _ = await ai_client.get_text_response(chat_history, user_content)
            db_user_content = user_content
            
        await db.add_message_to_history(user_id, char_name, 'user', db_user_content)
        await db.add_message_to_history(user_id, char_name, 'model', response_text)
        await send_long_message(update, response_text)
    except Exception as e:
        logger.error(f"Ошибка AI запроса для user_id={user_id}: {e}", exc_info=True)
        await update.message.reply_text("Произошла ошибка при обращении к AI.")

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await db.add_or_update_user(user.id, user.full_name, user.username)
    user_data = await db.get_user_by_telegram_id(user.id)
    if not user_data or not user_data.get('is_verified'):
        await captcha_handler.send_captcha(update, context)
        return
    welcome_text = (f"С возвращением, {user.mention_html()}!\n\n"
                    "Я твой многофункциональный ассистент. "
                    "Чтобы задать мне определенную роль или личность, воспользуйся меню <b>'Персонажи'</b>.")
    await update.message.reply_html(text=welcome_text, reply_markup=get_main_keyboard())

# <<< ИЗМЕНЕНИЕ: Применили декораторы и переписали логику >>>
@require_verification
@inject_user_data
async def reset_command(update: Update, context: ContextTypes.DEFAULT_TYPE, user_data: dict):
    # Логика теперь всегда едина: сбрасываем историю текущего персонажа
    char_name_to_reset = user_data.get('current_character_name', DEFAULT_CHARACTER_NAME)
    display_name = char_name_to_reset

    await db.clear_chat_history(user_data['id'], char_name_to_reset)
    await update.message.reply_text(f"История диалога с *{escape_markdown(display_name, version=2)}* очищена\\.", parse_mode='MarkdownV2')

@require_verification
async def set_subscription_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        logger.warning(f"Попытка несанкционированного доступа к /setsub от user_id={update.effective_user.id}")
        await update.message.reply_text("У вас нет прав для выполнения этой команды.")
        return
    try:
        if len(context.args) != 3: raise ValueError("Неверное количество аргументов.")
        target_user_id_str, tier, days_str = context.args
        target_user_id = int(target_user_id_str)
        days = int(days_str)
        if tier not in [TIER_LITE, TIER_PRO, TIER_FREE]:
            await update.message.reply_text(f"Неверный уровень: используйте '{TIER_LITE}', '{TIER_PRO}' или '{TIER_FREE}'")
            return
        await db.set_user_subscription(target_user_id, tier, days)
        await update.message.reply_text(f"Пользователю telegram_id={target_user_id} установлена подписка '{tier}' на {days} дней.")
    except Exception as e:
        await update.message.reply_text(f"Ошибка. Использование: /setsub <telegram_id> <tier> <days>\nПример: /setsub 12345 lite 30\nДетали: {e}")

@require_verification
async def show_wip_notice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("Этот раздел находится в разработке.")

# <<< ИЗМЕНЕНИЕ: Применили декоратор и упростили код >>>
@require_verification
@inject_user_data
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE, user_data: dict):
    # --- ШАГ 1: Проверка на специальные состояния (без изменений) ---
    if await characters_handler.handle_stateful_message(update, context):
        return

    # --- ШАГ 2: Проверка лимитов (теперь проще, т.к. user_data уже есть) ---
    tier_params = config.SUBSCRIPTION_TIERS[await get_actual_user_tier(user_data)]
    if tier_params['daily_limit'] is not None:
        usage = await db.get_and_update_user_usage(user_data['id'], tier_params['daily_limit'])
        if not usage["can_request"]:
            return await update.message.reply_text(f"Достигнут дневной лимит для тарифа '{tier_params['name']}'.")

    # --- ШАГ 3: Определяем тип контента (без изменений) ---
    user_content = None
    image_obj = None
    is_photo = False
    is_document = False
    document_char_count = 0 

    if update.message.photo:
        is_photo = True
        file_bytes = await (await context.bot.get_file(update.message.photo[-1].file_id)).download_as_bytearray()
        image_obj = Image.open(BytesIO(file_bytes))
        user_content = update.message.caption or "Опиши это изображение."
    
    elif update.message.document:
        is_document = True
        try:
            file_content = await get_text_content_from_document(update.message.document, context)
            document_char_count = len(file_content)
            task_prompt = update.message.caption or "Проанализируй и подробно ответь на основе следующего текста из файла:"
            user_content = f"{task_prompt}\n\n---\n\n{file_content}"
        except (ValueError, FileSizeError) as e:
            return await update.message.reply_text(f"Ошибка обработки файла: {e}")

    elif update.message.text:
        user_content = update.message.text

    # --- ШАГ 4: Отправляем запрос в AI, если контент был найден ---
    if not user_content:
        return

    await process_ai_request(
        update, 
        context, 
        user_data, # Передаем готовые данные пользователя
        user_content, 
        is_photo=is_photo, 
        image_obj=image_obj, 
        is_document=is_document, 
        document_char_count=document_char_count
    )

async def button_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await captcha_handler.handle_captcha_callback(update, context): return
    if await ai_selection_handler.handle_ai_selection_callback(update, context): return
    
    user_data = await db.get_user_by_telegram_id(update.effective_user.id)
    if not user_data or not user_data.get('is_verified'):
        await update.callback_query.answer("Пожалуйста, пройдите проверку, нажав /start", show_alert=True)
        return

    if await characters_handler.handle_character_callbacks(update, context): return
    if await profile_handler.handle_profile_callbacks(update, context): return
    await update.callback_query.answer("Это действие больше не актуально.")

async def post_init(application: Application):
    await application.bot.set_my_commands([BotCommand("start", "Начать/перезапустить"), BotCommand("reset", "Сбросить диалог")])

def main():
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).post_init(post_init).build()
    
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("reset", reset_command))
    app.add_handler(CommandHandler("setsub", set_subscription_command))
    
    app.add_handler(MessageHandler(filters.TEXT & filters.Regex("^Выбор AI$"), require_verification(ai_selection_handler.show_ai_mode_selection_hub))) 
    app.add_handler(MessageHandler(filters.TEXT & filters.Regex("^Персонажи$"), require_verification(character_menus.show_character_categories_menu)))
    app.add_handler(MessageHandler(filters.TEXT & filters.Regex("^Профиль$"), profile_handler.show_profile))
    app.add_handler(MessageHandler(filters.TEXT & filters.Regex("^Настройки$"), show_wip_notice))

    app.add_handler(MessageHandler((filters.TEXT & ~filters.COMMAND) | filters.PHOTO | filters.Document.MimeType("text/plain"), handle_message))
    
    app.add_handler(CallbackQueryHandler(button_callback_handler))
    
    logger.info("Бот запущен и готов к работе (Архитектура: Мульти-AI, Вариант 3)...")
    app.run_polling()

if __name__ == "__main__":
    main()  