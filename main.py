# main.py

import os
import logging
import asyncio
from dotenv import load_dotenv
from typing import List

# [Dev-Ассистент]: Импортируем CancelledError для правильной обработки остановки фоновых задач
from asyncio import CancelledError

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

def parse_admin_ids(ids_string: str) -> List[int]:
    admin_ids = []
    for admin_id_str in ids_string.split(','):
        cleaned_id_str = admin_id_str.strip()
        if not cleaned_id_str: continue
        try: admin_ids.append(int(cleaned_id_str))
        except ValueError: logger.warning(f"Не удалось преобразовать ID администратора '{cleaned_id_str}'.")
    return admin_ids

load_dotenv()
admin_ids_from_env = os.getenv("ADMIN_IDS", "")
ADMIN_IDS = parse_admin_ids(admin_ids_from_env)
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

from io import BytesIO
from PIL import Image
from telegram import Update, BotCommand, InlineKeyboardButton, InlineKeyboardMarkup, Bot
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
from telegram.constants import ChatAction
import database as db
import config
import html
from constants import (
    STATE_NONE, STATE_WAITING_FOR_IMAGE_PROMPT, TIER_LITE, TIER_PRO, 
    TIER_FREE, GPT_4_1_NANO, CURRENT_IMAGE_GEN_PROVIDER_KEY, 
    IMAGE_GEN_DALL_E_3, IMAGE_GEN_YANDEXART, GEMINI_STANDARD, 
    LAST_IMAGE_PROMPT_KEY, LAST_RESPONSE_KEY, OUTPUT_FORMAT_TEXT
)
from characters import DEFAULT_CHARACTER_NAME, ALL_PROMPTS
from handlers import character_menus, characters_handler, profile_handler, captcha_handler, ai_selection_handler, onboarding_handler, post_processing_handler
import utils
from utils import get_main_keyboard, get_actual_user_tier, require_verification, get_text_content_from_document, FileSizeError, inject_user_data
from ai_clients.factory import get_ai_client_with_caps
from ai_clients.gpt_client import GPTClient
from ai_clients.yandexart_client import YandexArtClient

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")


# [Dev-Ассистент]: НАША НОВАЯ ФОНОВАЯ ЗАДАЧА-"ПОМОЩНИК".
# [Dev-Ассистент]: В цикле отправляет указанное действие (action) каждые 4 секунды,
# [Dev-Ассистент]: чтобы индикатор в чате не пропадал.
async def _keep_indicator_alive(bot: Bot, chat_id: int, action: str):
    try:
        while True:
            await bot.send_chat_action(chat_id=chat_id, action=action)
            await asyncio.sleep(4)
    except CancelledError:
        logger.debug(f"Задача индикатора '{action}' для чата {chat_id} отменена.")
        raise
    except Exception as e:
        logger.warning(f"Ошибка в задаче индикатора для чата {chat_id}: {e}")

# [Dev-Ассистент]: Мы будем использовать эту же функцию для текстовых запросов,
# [Dev-Ассистент]: поэтому она переименована и сделана более универсальной.
async def _keep_typing_indicator_alive(bot: Bot, chat_id: int):
    # [Dev-Ассистент]: Вызываем нашу новую универсальную функцию с нужным действием.
    await _keep_indicator_alive(bot, chat_id, ChatAction.TYPING)


async def process_ai_request(update: Update, context: ContextTypes.DEFAULT_TYPE, user_data: dict, user_content: str, is_photo: bool = False, image_obj: Image = None, is_document: bool = False, document_char_count: int = 0):
    user_id = user_data['id']
    chat_id = update.effective_chat.id
    char_name = user_data.get('current_character_name', DEFAULT_CHARACTER_NAME)
    ai_provider = await utils.get_user_ai_provider(user_data)
    output_format = user_data.get('output_format', OUTPUT_FORMAT_TEXT)

    system_instruction = "Ты — полезный ассистент."
    custom_char = await db.get_custom_character_by_name(user_id, char_name)
    if custom_char:
        system_instruction = custom_char['prompt']
    else:
        char_info = ALL_PROMPTS.get(char_name)
        if char_info:
            system_instruction = char_info.get('prompt', system_instruction)

    try:
        caps = get_ai_client_with_caps(ai_provider, system_instruction)
        ai_client = caps.client
    except ValueError as e:
        logger.error(f"Ошибка создания AI клиента: {e}")
        await context.bot.send_message(chat_id=chat_id, text=f"Ошибка конфигурации: {e}")
        return
    
    if is_photo and not caps.supports_vision:
        await context.bot.send_message(chat_id=chat_id, text="К сожалению, выбранная модель AI не умеет обрабатывать изображения.")
        return
    if is_document and caps.file_char_limit == 0:
        await context.bot.send_message(chat_id=chat_id, text="Обработка файлов для выбранной модели AI не поддерживается.")
        return
    if is_document and document_char_count > caps.file_char_limit:
        await context.bot.send_message(chat_id=chat_id, text=f"Файл слишком большой. Максимум: {caps.file_char_limit} символов, в вашем файле: {document_char_count}.")
        return

    history_from_db = await db.get_chat_history(user_id, char_name, limit=config.DEFAULT_HISTORY_LIMIT)
    chat_history = history_from_db + context.chat_data.get('history', [])
    context.chat_data.pop('history', None)

    # [Dev-Ассистент]: Запускаем индикатор "печатает..."
    indicator_task = asyncio.create_task(
        _keep_typing_indicator_alive(context.bot, chat_id)
    )
    
    raw_response_text = None
    processed_html_text = None
    reply_markup = None

    try:
        if is_photo and image_obj:
            raw_response_text, _ = await ai_client.get_image_response(chat_history, user_content, image_obj)
            db_user_content = f"[Изображение] {user_content}"
        else:
            raw_response_text, _ = await ai_client.get_text_response(chat_history, user_content)
            db_user_content = user_content
            
        await db.add_message_to_history(user_id, char_name, 'user', db_user_content)
        await db.add_message_to_history(user_id, char_name, 'model', raw_response_text)

        context.user_data[LAST_RESPONSE_KEY] = raw_response_text
        reply_markup = post_processing_handler.get_post_processing_keyboard(len(raw_response_text))
        
        processed_html_text = utils.markdown_to_html(raw_response_text)

    except Exception as e:
        logger.error(f"Ошибка AI запроса для user_id={user_id}: {e}", exc_info=True)
        processed_html_text = "<b>Произошла ошибка при обращении к AI.</b>"
    
    finally:
        indicator_task.cancel()
        try:
            await indicator_task
        except CancelledError:
            pass
        
        if processed_html_text:
            final_reply_markup = reply_markup if "ошибка" not in processed_html_text else None
            await utils.send_long_message(
                update, context, 
                text=processed_html_text,
                reply_markup=final_reply_markup, 
                output_format=output_format
            )

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # ... (код без изменений)
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

@require_verification
@inject_user_data
async def reset_command(update: Update, context: ContextTypes.DEFAULT_TYPE, user_data: dict):
    # ... (код без изменений)
    char_name_to_reset = user_data.get('current_character_name', DEFAULT_CHARACTER_NAME)
    display_name = char_name_to_reset
    await db.clear_chat_history(user_data['id'], char_name_to_reset)
    safe_display_name = html.escape(display_name)
    await update.message.reply_text(f"История диалога с <b>{safe_display_name}</b> очищена.", parse_mode='HTML')

@require_verification
async def set_subscription_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # ... (код без изменений)
    if update.effective_user.id not in ADMIN_IDS:
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

@require_verification
@inject_user_data
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE, user_data: dict):
    current_state = context.user_data.get('state', STATE_NONE)

    if current_state == STATE_WAITING_FOR_IMAGE_PROMPT:
        # [Dev-Ассистент]: Мы по-прежнему сохраняем оригинальный текст,
        # [Dev-Ассистент]: чтобы показать его пользователю в подписи к фото.
        original_prompt_text = update.message.text
        if not original_prompt_text:
            await update.message.reply_text("Пожалуйста, отправьте текстовое описание для картинки.")
            return

        # [Dev-Ассистент]: !!! РЕШЕНИЕ !!!
        # [Dev-Ассистент]: Вызываем нашу новую функцию из utils для "очистки" промпта.
        # [Dev-Ассистент]: Именно эту чистую версию мы будем отправлять в API.
        clean_prompt_text = utils.strip_markdown_for_prompt(original_prompt_text)

        image_gen_provider = context.user_data.get(CURRENT_IMAGE_GEN_PROVIDER_KEY)
        # [Dev-Ассистент]: Сохраняем в историю оригинальный текст, а не очищенный
        context.user_data[LAST_IMAGE_PROMPT_KEY] = original_prompt_text
        
        keyboard = [
            [
                InlineKeyboardButton("🔄 Перерисовать", callback_data="image_redraw"),
                InlineKeyboardButton("✨ Создать новое", callback_data="image_create_new")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        indicator_task = None
        
        try:
            if image_gen_provider == IMAGE_GEN_DALL_E_3:
                await update.message.reply_text("🎨 Принято! Начинаю рисовать через DALL-E 3, это может занять до минуты...")
                indicator_task = asyncio.create_task(
                    _keep_indicator_alive(context.bot, update.effective_chat.id, ChatAction.UPLOAD_PHOTO)
                )
                
                caps = get_ai_client_with_caps(GPT_4_1_NANO, system_instruction="You are an image generation assistant.")
                # [Dev-Ассистент]: Отправляем в API ОЧИЩЕННЫЙ текст
                image_url, error_message = await caps.client.generate_image(clean_prompt_text)

                if error_message:
                    await update.message.reply_text(f"😔 Ошибка: {error_message}")
                elif image_url:
                    # [Dev-Ассистент]: А в подписи показываем ОРИГИНАЛЬНЫЙ текст
                    await update.message.reply_photo(
                        photo=image_url, 
                        caption=f"✨ Ваше изображение по запросу:\n\n`{original_prompt_text}`", 
                        parse_mode='Markdown',
                        reply_markup=reply_markup
                    )
                    context.user_data['state'] = STATE_NONE
                # ...

            elif image_gen_provider == IMAGE_GEN_YANDEXART:
                # ...
                indicator_task = asyncio.create_task(
                    _keep_indicator_alive(context.bot, update.effective_chat.id, ChatAction.UPLOAD_PHOTO)
                )
                
                yandex_client = YandexArtClient(
                    folder_id=os.getenv("YANDEX_FOLDER_ID"),
                    api_key=os.getenv("YANDEX_API_KEY")
                )
                # [Dev-Ассистент]: Отправляем в API ОЧИЩЕННЫЙ текст и здесь
                image_bytes, error_message = await yandex_client.generate_image(clean_prompt_text)

                if error_message:
                    await update.message.reply_text(f"😔 Ошибка: {error_message}")
                elif image_bytes:
                     # [Dev-Ассистент]: И здесь в подписи показываем ОРИГИНАЛЬНЫЙ текст
                    await update.message.reply_photo(
                        photo=image_bytes, 
                        caption=f"✨ Ваше изображение от YandexArt по запросу:\n\n`{original_prompt_text}`", 
                        parse_mode='Markdown',
                        reply_markup=reply_markup
                    )
                    context.user_data['state'] = STATE_NONE
                else:
                    await update.message.reply_text("Произошла неизвестная ошибка, картинка не была получена.")
            
            else:
                await update.message.reply_text("Произошла ошибка: не выбран AI для генерации. Пожалуйста, начните сначала из меню.")
                context.user_data['state'] = STATE_NONE
        
        except Exception as e:
            logger.error(f"Критическая ошибка в блоке генерации изображений: {e}", exc_info=True)
            await update.message.reply_text(f"Произошла критическая ошибка: {e}")

        finally:
            # [Dev-Ассистент]: Гарантированно останавливаем "помощника"
            if indicator_task:
                indicator_task.cancel()
                try:
                    await indicator_task
                except CancelledError:
                    pass # Это ожидаемое и нормальное завершение, игнорируем.
        
        return
    
    if await characters_handler.handle_stateful_message(update, context):
        return
    
    tier_params = config.SUBSCRIPTION_TIERS[await get_actual_user_tier(user_data)]
    if tier_params['daily_limit'] is not None:
        usage = await db.get_and_update_user_usage(user_data['id'], tier_params['daily_limit'])
        if not usage["can_request"]:
            return await update.message.reply_text(f"Достигнут дневной лимит для тарифа '{tier_params['name']}'.")
            
    user_content, image_obj, is_photo, is_document, document_char_count = None, None, False, False, 0
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
        
    if not user_content: return
    
    await process_ai_request(update, context, user_data, user_content, is_photo=is_photo, image_obj=image_obj, is_document=is_document, document_char_count=document_char_count)

@require_verification
@inject_user_data
async def handle_voice_message(update: Update, context: ContextTypes.DEFAULT_TYPE, user_data: dict):
    # ... (код без изменений)
    tier_params = config.SUBSCRIPTION_TIERS[await get_actual_user_tier(user_data)]
    if tier_params['daily_limit'] is not None:
        usage = await db.get_and_update_user_usage(user_data['id'], tier_params['daily_limit'])
        if not usage["can_request"]:
            return await update.message.reply_text(f"Достигнут дневной лимит для тарифа '{tier_params['name']}'.")

    status_message = await update.message.reply_text("🎙️ Получил голосовое, расшифровываю...")
    
    try:
        voice_file = await context.bot.get_file(update.message.voice.file_id)
        oga_bytes = await voice_file.download_as_bytearray()
        
        loop = asyncio.get_running_loop()
        mp3_bytes = await loop.run_in_executor(None, utils.convert_oga_to_mp3_in_memory, oga_bytes)
        
        if not OPENAI_API_KEY:
            raise ValueError("API ключ для OpenAI (необходим для Whisper) не найден в .env")

        gpt_client_for_whisper = GPTClient(api_key=OPENAI_API_KEY, system_instruction="", model_name="")
        recognized_text = await gpt_client_for_whisper.transcribe_audio(mp3_bytes)
        
        if recognized_text:
            await status_message.edit_text(f"<i>Распознанный текст:</i>\n\n«{recognized_text}»\n\n🧠 Отправляю на обработку...", parse_mode='HTML')
            await process_ai_request(update, context, user_data, user_content=recognized_text)
        else:
            await status_message.edit_text("😔 Не удалось распознать речь в вашем сообщении. Пожалуйста, попробуйте еще раз.")

    except ValueError as e:
        await status_message.edit_text(f"Ошибка конфигурации: {e}")
    except Exception as e:
        logger.error(f"Критическая ошибка при обработке голосового сообщения: {e}", exc_info=True)
        if "No such file or directory: 'ffmpeg'" in str(e) or "Cannot find specified file" in str(e):
             await status_message.edit_text("Ошибка: для распознавания голоса на сервере должна быть установлена утилита `ffmpeg`.")
        else:
            await status_message.edit_text("Произошла неизвестная ошибка при обработке вашего голосового сообщения.")


async def button_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # ... (код без изменений)
    if await post_processing_handler.handle_post_processing_callback(update, context): return
    if await captcha_handler.handle_captcha_callback(update, context): return
    if await ai_selection_handler.handle_ai_selection_callback(update, context): return
    if await onboarding_handler.handle_onboarding_callback(update, context): return
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
    app = (
        Application.builder()
        .token(TELEGRAM_BOT_TOKEN)
        .post_init(post_init)
        .read_timeout(120)
        .write_timeout(120)
        .build()
    )
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("reset", reset_command))
    app.add_handler(CommandHandler("setsub", set_subscription_command))
    app.add_handler(MessageHandler(filters.TEXT & filters.Regex("^Выбор AI$"), require_verification(ai_selection_handler.show_ai_mode_selection_hub)))
    app.add_handler(MessageHandler(filters.TEXT & filters.Regex("^Персонажи$"), require_verification(character_menus.show_character_categories_menu)))
    app.add_handler(MessageHandler(filters.TEXT & filters.Regex("^⚙️ Профиль$"), profile_handler.show_profile_hub))
    app.add_handler(MessageHandler(filters.TEXT & filters.Regex("^🤖 AGM, научи меня!$"), require_verification(onboarding_handler.start_onboarding)))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice_message))
    app.add_handler(MessageHandler((filters.TEXT & ~filters.COMMAND) | filters.PHOTO | filters.Document.MimeType("text/plain"), handle_message))
    app.add_handler(CallbackQueryHandler(button_callback_handler))
    
    logger.info("Бот запущен и готов к работе...")
    try:
        app.run_polling()
    except KeyboardInterrupt:
        logger.info("Получен сигнал KeyboardInterrupt, бот останавливается.")
    except Exception as e:
        logger.critical(f"Произошла критическая ошибка при запуске бота: {e}", exc_info=True)

if __name__ == "__main__":
    main()