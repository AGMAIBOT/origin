# main.py

import os
import logging
# [Dev-Ассистент]: Новый импорт для асинхронных операций
import asyncio
from dotenv import load_dotenv
from typing import List
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

# [Dev-Ассистент]: Загружаем ключ OpenAI для транскрипции
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

from io import BytesIO
from asyncio import CancelledError
from PIL import Image
from telegram import Update, BotCommand, InlineKeyboardButton, InlineKeyboardMarkup, Bot
# [Dev-Ассистент]: Добавляем filters.VOICE для обработки голосовых
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
from telegram.helpers import escape_markdown
from telegram.constants import ChatAction
from google.api_core.exceptions import ResourceExhausted
import database as db
import config
import html
from constants import (
    STATE_NONE, STATE_WAITING_FOR_IMAGE_PROMPT, TIER_LITE, TIER_PRO, 
    TIER_FREE, GPT_4_OMNI, CURRENT_IMAGE_GEN_PROVIDER_KEY, 
    IMAGE_GEN_DALL_E_3, IMAGE_GEN_YANDEXART, GEMINI_STANDARD, 
    LAST_IMAGE_PROMPT_KEY, LAST_RESPONSE_KEY, OUTPUT_FORMAT_TEXT
)
from handlers.post_processing_handler import get_post_processing_keyboard
from characters import DEFAULT_CHARACTER_NAME, ALL_PROMPTS
from handlers import character_menus, characters_handler, profile_handler, captcha_handler, ai_selection_handler, onboarding_handler, post_processing_handler
# [Dev-Ассистент]: Импортируем нашу новую утилиту и GPTClient для Whisper
import utils
from utils import get_main_keyboard, send_long_message, get_actual_user_tier, require_verification, get_text_content_from_document, FileSizeError, inject_user_data
from ai_clients.factory import get_ai_client_with_caps
from ai_clients.gpt_client import GPTClient
from ai_clients.yandexart_client import YandexArtClient
from handlers.post_processing_handler import get_post_processing_keyboard

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

async def _keep_typing_indicator_alive(bot: Bot, chat_id: int):
    """
    [Dev-Ассистент]: НАША НОВАЯ ФОНОВАЯ ЗАДАЧА.
    В цикле отправляет действие 'typing' каждые 4 секунды.
    """
    try:
        while True:
            await bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
            await asyncio.sleep(4)
    except CancelledError:
        # [Dev-Ассистент]: Это ожидаемая ошибка, когда мы останавливаем задачу.
        # [Dev-Ассистент]: Она нужна, чтобы чисто выйти из цикла.
        logger.debug(f"Задача индикатора для чата {chat_id} отменена.")
        # [Dev-Ассистент]: Перебрасываем ошибку, чтобы asyncio понял, что задача действительно завершилась.
        raise
    except Exception as e:
        # [Dev-Ассистент]: Логируем любые другие, неожиданные ошибки.
        logger.warning(f"Ошибка в задаче индикатора для чата {chat_id}: {e}")

async def process_ai_request(update: Update, context: ContextTypes.DEFAULT_TYPE, user_data: dict, user_content: str, is_photo: bool = False, image_obj: Image = None, is_document: bool = False, document_char_count: int = 0):
    """
    [Dev-Ассистент]: Полностью переработанная функция с надежным потоком данных.
    1. Получает "сырой" ответ от LLM.
    2. Сохраняет "сырой" ответ в БД.
    3. Обрабатывает ответ для нужного формата вывода (HTML или очистка для файлов).
    4. Отправляет пользователю обработанный результат.
    """
    # --- Шаг 1: Подготовка данных ---
    user_id = user_data['id']
    chat_id = update.effective_chat.id
    char_name = user_data.get('current_character_name', DEFAULT_CHARACTER_NAME)
    ai_provider = user_data.get('current_ai_provider') or GEMINI_STANDARD
    output_format = user_data.get('output_format', OUTPUT_FORMAT_TEXT)

    # --- Шаг 2: Получение системной инструкции ---
    system_instruction = "Ты — полезный ассистент."
    custom_char = await db.get_custom_character_by_name(user_id, char_name)
    if custom_char:
        system_instruction = custom_char['prompt']
    else:
        char_info = ALL_PROMPTS.get(char_name)
        if char_info:
            system_instruction = char_info.get('prompt', system_instruction)

    # --- Шаг 3: Создание AI клиента и проверка возможностей ---
    try:
        caps = get_ai_client_with_caps(ai_provider, system_instruction)
        ai_client = caps.client
    except ValueError as e:
        logger.error(f"Ошибка создания AI клиента: {e}")
        await context.bot.send_message(chat_id=chat_id, text=f"Ошибка конфигурации: {e}")
        return
    
    # [Dev-Ассистент]: Проверки на Vision и обработку файлов (без изменений)
    if is_photo and not caps.supports_vision:
        await context.bot.send_message(chat_id=chat_id, text="К сожалению, выбранная модель AI не умеет обрабатывать изображения.")
        return
    if is_document and caps.file_char_limit == 0:
        await context.bot.send_message(chat_id=chat_id, text="Обработка файлов для выбранной модели AI не поддерживается.")
        return
    if is_document and document_char_count > caps.file_char_limit:
        await context.bot.send_message(chat_id=chat_id, text=f"Файл слишком большой. Максимум: {caps.file_char_limit} символов, в вашем файле: {document_char_count}.")
        return

    # --- Шаг 4: Работа с историей чата ---
    history_from_db = await db.get_chat_history(user_id, char_name, limit=config.DEFAULT_HISTORY_LIMIT)
    chat_history = history_from_db + context.chat_data.get('history', [])
    context.chat_data.pop('history', None)

    # --- Запускаем "умный индикатор" ---
    indicator_task = asyncio.create_task(
        _keep_typing_indicator_alive(context.bot, chat_id)
    )
    
    raw_response_text = None
    processed_text_for_user = None
    reply_markup = None

    try:
        # --- Шаг 5: Получение СЫРОГО ответа от LLM ---
        if is_photo and image_obj:
            raw_response_text, _ = await ai_client.get_image_response(chat_history, user_content, image_obj)
            db_user_content = f"[Изображение] {user_content}"
        else:
            raw_response_text, _ = await ai_client.get_text_response(chat_history, user_content)
            db_user_content = user_content
            
        # --- Шаг 6: Сохранение СЫРОГО ответа в БД ---
        await db.add_message_to_history(user_id, char_name, 'user', db_user_content)
        await db.add_message_to_history(user_id, char_name, 'model', raw_response_text)

        # --- Шаг 7: Постобработка для пользователя ---
        context.user_data[LAST_RESPONSE_KEY] = raw_response_text
        reply_markup = get_post_processing_keyboard(len(raw_response_text))
        
        # [Dev-Ассистент]: Если выводим как текст, конвертируем в HTML.
        # [Dev-Ассистент]: Если выводим как файл (TXT/PDF), передаем "сырой" текст,
        # [Dev-Ассистент]: а `send_long_message` сама очистит его от разметки.
        if output_format == OUTPUT_FORMAT_TEXT:
            processed_text_for_user = utils.markdown_to_html(raw_response_text)
        else:
            processed_text_for_user = raw_response_text

    except Exception as e:
        logger.error(f"Ошибка AI запроса для user_id={user_id}: {e}", exc_info=True)
        # В случае ошибки, текст будет простым, без разметки
        processed_text_for_user = "Произошла ошибка при обращении к AI."
    
    finally:
        # --- Гарантированная остановка индикатора ---
        indicator_task.cancel()
        try:
            await indicator_task
        except CancelledError:
            pass
        
        # --- Шаг 8: Отправка финального результата пользователю ---
        if processed_text_for_user:
            # [Dev-Ассистент]: Определяем, нужно ли показывать кнопки пост-обработки
            final_reply_markup = reply_markup if "ошибка" not in processed_text_for_user else None
            
            await utils.send_long_message(
                update, context, 
                text=processed_text_for_user,
                reply_markup=final_reply_markup, 
                output_format=output_format
            )

# ... (команды start, reset, set_subscription, show_wip_notice остаются без изменений) ...
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

@require_verification
@inject_user_data
async def reset_command(update: Update, context: ContextTypes.DEFAULT_TYPE, user_data: dict):
    char_name_to_reset = user_data.get('current_character_name', DEFAULT_CHARACTER_NAME)
    display_name = char_name_to_reset
    await db.clear_chat_history(user_data['id'], char_name_to_reset)
    
    # [Dev-Ассистент]: Переходим на HTML
    safe_display_name = html.escape(display_name)
    await update.message.reply_text(f"История диалога с <b>{safe_display_name}</b> очищена.", parse_mode='HTML')

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
    
@require_verification
@inject_user_data
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE, user_data: dict):
    current_state = context.user_data.get('state', STATE_NONE)

    if current_state == STATE_WAITING_FOR_IMAGE_PROMPT:
        prompt_text = update.message.text
        if not prompt_text:
            await update.message.reply_text("Пожалуйста, отправьте текстовое описание для картинки.")
            return

        image_gen_provider = context.user_data.get(CURRENT_IMAGE_GEN_PROVIDER_KEY)
        context.user_data[LAST_IMAGE_PROMPT_KEY] = prompt_text

        # --- Логика для DALL-E 3 (ЗДЕСЬ БУДУТ ИЗМЕНЕНИЯ) ---
        if image_gen_provider == IMAGE_GEN_DALL_E_3:
            await update.message.reply_text("🎨 Принято! Начинаю рисовать через DALL-E 3, это может занять до минуты...")
            await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.UPLOAD_PHOTO)
            try:
                caps = get_ai_client_with_caps(GPT_4_OMNI, system_instruction="You are an image generation assistant.")
                image_url, error_message = await caps.client.generate_image(prompt_text)

                if error_message:
                    await update.message.reply_text(f"😔 Ошибка: {error_message}")
                elif image_url:
                    # [Dev-Ассистент]: НАЧАЛО ИЗМЕНЕНИЯ.
                    # [Dev-Ассистент]: Создаем и прикрепляем ту же самую клавиатуру, что и для YandexArt.
                    keyboard = [
                        [
                            InlineKeyboardButton("🔄 Перерисовать", callback_data="image_redraw"),
                            InlineKeyboardButton("✨ Создать новое", callback_data="image_create_new")
                        ]
                    ]
                    reply_markup = InlineKeyboardMarkup(keyboard)

                    await update.message.reply_photo(
                        photo=image_url, 
                        caption=f"✨ Ваше изображение по запросу:\n\n`{prompt_text}`", 
                        parse_mode='Markdown',
                        reply_markup=reply_markup # <<< [Dev-Ассистент]: Прикрепляем клавиатуру
                    )
                    # [Dev-Ассистент]: КОНЕЦ ИЗМЕНЕНИЯ.
                    context.user_data['state'] = STATE_NONE
                else:
                    await update.message.reply_text("Произошла неизвестная ошибка, картинка не была получена.")
            except Exception as e:
                logger.error(f"Критическая ошибка в блоке генерации DALL-E 3: {e}", exc_info=True)
                await update.message.reply_text(f"Произошла критическая ошибка: {e}")

        # --- Логика для YandexArt (Остается без изменений) ---
        elif image_gen_provider == IMAGE_GEN_YANDEXART:
            # ... код для YandexArt остается без изменений
            if len(prompt_text) > config.YANDEXART_PROMPT_LIMIT:
                cancel_button = InlineKeyboardButton("❌ Отмена", callback_data="image_gen_cancel")
                reply_markup = InlineKeyboardMarkup([[cancel_button]])
                await update.message.reply_text(
                    f"😔 Ваш запрос для YandexArt слишком длинный.\n\n"
                    f"Максимум: {config.YANDEXART_PROMPT_LIMIT} символов. У вас: {len(prompt_text)}.\n\n"
                    f"Пожалуйста, сократите описание и попробуйте снова, или отмените операцию.",
                    reply_markup=reply_markup
                )
                return

            await update.message.reply_text("🎨 Принято! Отправляю запрос в YandexArt, это может занять до 2 минут...")
            await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.UPLOAD_PHOTO)
            
            try:
                yandex_client = YandexArtClient(
                    folder_id=os.getenv("YANDEX_FOLDER_ID"),
                    api_key=os.getenv("YANDEX_API_KEY")
                )
                image_bytes, error_message = await yandex_client.generate_image(prompt_text)

                if error_message:
                    await update.message.reply_text(f"😔 Ошибка: {error_message}")
                elif image_bytes:
                    keyboard = [
                        [
                            InlineKeyboardButton("🔄 Перерисовать", callback_data="image_redraw"),
                            InlineKeyboardButton("✨ Создать новое", callback_data="image_create_new")
                        ]
                    ]
                    reply_markup = InlineKeyboardMarkup(keyboard)

                    await update.message.reply_photo(
                        photo=image_bytes, 
                        caption=f"✨ Ваше изображение от YandexArt по запросу:\n\n`{prompt_text}`", 
                        parse_mode='Markdown',
                        reply_markup=reply_markup
                    )
                    
                    context.user_data['state'] = STATE_NONE
                else:
                    await update.message.reply_text("Произошла неизвестная ошибка, картинка не была получена.")
            except Exception as e:
                logger.error(f"Критическая ошибка в блоке генерации YandexArt: {e}", exc_info=True)
                await update.message.reply_text(f"Произошла критическая ошибка: {e}")
        else:
            await update.message.reply_text("Произошла ошибка: не выбран AI для генерации. Пожалуйста, начните сначала из меню.")
            context.user_data['state'] = STATE_NONE
        
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

# [Dev-Ассистент]: НОВЫЙ ОБРАБОТЧИК ДЛЯ ГОЛОСОВЫХ СООБЩЕНИЙ
@require_verification
@inject_user_data
async def handle_voice_message(update: Update, context: ContextTypes.DEFAULT_TYPE, user_data: dict):
    """Обрабатывает входящие голосовые сообщения."""
    
    # 1. Проверяем лимиты, как в обычном сообщении
    tier_params = config.SUBSCRIPTION_TIERS[await get_actual_user_tier(user_data)]
    if tier_params['daily_limit'] is not None:
        usage = await db.get_and_update_user_usage(user_data['id'], tier_params['daily_limit'])
        if not usage["can_request"]:
            return await update.message.reply_text(f"Достигнут дневной лимит для тарифа '{tier_params['name']}'.")

    # 2. Информируем пользователя, что мы начали работать
    status_message = await update.message.reply_text("🎙️ Получил голосовое, расшифровываю...")
    
    try:
        # 3. Скачиваем аудиофайл
        voice_file = await context.bot.get_file(update.message.voice.file_id)
        oga_bytes = await voice_file.download_as_bytearray()
        
        # 4. Конвертируем OGA в MP3
        loop = asyncio.get_running_loop()
        mp3_bytes = await loop.run_in_executor(None, utils.convert_oga_to_mp3_in_memory, oga_bytes)
        
        # 5. Отправляем на транскрипцию в Whisper
        # Для доступа к Whisper нам нужен ключ OpenAI
        if not OPENAI_API_KEY:
            raise ValueError("API ключ для OpenAI (необходим для Whisper) не найден в .env")

        # Создаем временный клиент GPT только для этой задачи
        # Системная инструкция и модель не важны, т.к. мы вызываем другой метод
        gpt_client_for_whisper = GPTClient(api_key=OPENAI_API_KEY, system_instruction="", model_name="")
        recognized_text = await gpt_client_for_whisper.transcribe_audio(mp3_bytes)
        
        # 6. Обрабатываем результат
        if recognized_text:
            await status_message.edit_text(f"<i>Распознанный текст:</i>\n\n«{recognized_text}»\n\n🧠 Отправляю на обработку...", parse_mode='HTML')
            # Передаем распознанный текст в нашу основную функцию-обработчик
            await process_ai_request(update, context, user_data, user_content=recognized_text)
        else:
            await status_message.edit_text("😔 Не удалось распознать речь в вашем сообщении. Пожалуйста, попробуйте еще раз.")

    except ValueError as e:
        logger.error(f"Ошибка конфигурации при обработке голоса: {e}")
        await status_message.edit_text(f"Ошибка конфигурации: {e}")
    except Exception as e:
        logger.error(f"Критическая ошибка при обработке голосового сообщения: {e}", exc_info=True)
        # Проверяем на ошибку отсутствия ffmpeg
        if "No such file or directory: 'ffmpeg'" in str(e) or "Cannot find specified file" in str(e):
             await status_message.edit_text("Ошибка: для распознавания голоса на сервере должна быть установлена утилита `ffmpeg`.")
        else:
            await status_message.edit_text("Произошла неизвестная ошибка при обработке вашего голосового сообщения.")

async def button_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # [Dev-Ассистент]: Добавляем вызов нового обработчика в самое начало.
    if await post_processing_handler.handle_post_processing_callback(update, context): return
    if await captcha_handler.handle_captcha_callback(update, context): return
    # ... остальная часть функции без изменений
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
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).post_init(post_init).build()
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("reset", reset_command))
    app.add_handler(CommandHandler("setsub", set_subscription_command))
    app.add_handler(MessageHandler(filters.TEXT & filters.Regex("^Выбор AI$"), require_verification(ai_selection_handler.show_ai_mode_selection_hub)))
    app.add_handler(MessageHandler(filters.TEXT & filters.Regex("^Персонажи$"), require_verification(character_menus.show_character_categories_menu)))
    app.add_handler(MessageHandler(filters.TEXT & filters.Regex("^⚙️ Профиль$"), profile_handler.show_profile_hub))
    app.add_handler(MessageHandler(filters.TEXT & filters.Regex("^🤖 AGM, научи меня!$"), require_verification(onboarding_handler.start_onboarding)))
    
    # [Dev-Ассистент]: Регистрируем новый обработчик для голоса
    app.add_handler(MessageHandler(filters.VOICE, handle_voice_message))
    
    app.add_handler(MessageHandler((filters.TEXT & ~filters.COMMAND) | filters.PHOTO | filters.Document.MimeType("text/plain"), handle_message))
    app.add_handler(CallbackQueryHandler(button_callback_handler))
    logger.info("Бот запущен и готов к работе...")
    app.run_polling()

if __name__ == "__main__":
    main()