# handlers/ai_selection_handler.py (РЕФАКТОРИНГ НА HTML)

import html
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.error import BadRequest
import database as db
import config
from utils import get_actual_user_tier, get_user_ai_provider
from constants import (
    TIER_PRO, GEMINI_STANDARD, OPENROUTER_DEEPSEEK, GPT_1, GPT_2,
    OPENROUTER_GEMINI_2_FLASH, STATE_WAITING_FOR_IMAGE_PROMPT, STATE_NONE,
    IMAGE_GEN_DALL_E_3, IMAGE_GEN_YANDEXART, CURRENT_IMAGE_GEN_PROVIDER_KEY,
    LAST_IMAGE_PROMPT_KEY, TIER_PRO, TIER_LITE
)
from ai_clients.yandexart_client import YandexArtClient
from ai_clients.factory import get_ai_client_with_caps
from telegram.constants import ChatAction
import os

logger = logging.getLogger(__name__)

async def show_ai_mode_selection_hub(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['state'] = STATE_NONE

    text = "🤖 <b>Выберите режим работы AI</b>\n\nВыберите, что вы хотите делать: общаться с текстовой моделью или генерировать/редактировать изображения."
    keyboard = [
        [InlineKeyboardButton("📝 Текстовые модели", callback_data="select_mode_text")],
        [InlineKeyboardButton("🎨 Генерация изображений", callback_data="select_mode_image")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    if update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=reply_markup, parse_mode='HTML')
    else:
        await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='HTML')

async def show_text_ai_selection_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_data = await db.get_user_by_telegram_id(update.effective_user.id)
    # [Dev-Ассистент]: Определяем текущую активную модель через нашу "умную" функцию
    current_provider = await get_user_ai_provider(user_data)
    # [Dev-Ассистент]: Определяем тариф пользователя
    user_tier = await get_actual_user_tier(user_data)
    # [Dev-Ассистент]: Получаем "связку ключей" для его тарифа
    available_providers_for_tier = config.SUBSCRIPTION_TIERS[user_tier]['available_providers']
    
    text = (
        "📝 <b>Выберите текстовую модель ИИ</b>\n\n"
        "Режим \"Персонажи\" теперь работает со всеми моделями. Вы можете бесшовно переключаться между ними, сохраняя историю диалога.\n\n"
        "Ваш текущий выбор:"
    )
    
    keyboard = []
    # [Dev-Ассистент]: Динамически строим клавиатуру на основе мастер-списка
    for model_info in config.ALL_TEXT_MODELS_FOR_SELECTION:
        provider_id = model_info['provider_id']
        display_name = model_info['display_name']
        
        prefix = ""
        # 1. Проверяем, активна ли эта модель сейчас
        if provider_id == current_provider:
            prefix = "✅ "
        # 2. Если не активна, проверяем, доступна ли она на этом тарифе
        elif provider_id not in available_providers_for_tier:
            prefix = "🔒 "
            
        keyboard.append([
            InlineKeyboardButton(prefix + display_name, callback_data=f"select_ai_{provider_id}")
        ])

    keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data="back_to_ai_mode_hub")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.callback_query.edit_message_text(text, reply_markup=reply_markup, parse_mode='HTML')

async def show_image_ai_selection_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = "🎨 <b>Работа с изображениями</b>\n\nВыберите, что вы хотите сделать:"
    keyboard = [
        [InlineKeyboardButton("✨ Создать новое", callback_data="image_gen_create")],
        [InlineKeyboardButton("✍️ Редактировать (в разработке)", callback_data="image_edit_wip")],
        [InlineKeyboardButton("⬅️ Назад", callback_data="back_to_ai_mode_hub")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.callback_query.edit_message_text(text, reply_markup=reply_markup, parse_mode='HTML')

async def show_image_generation_ai_selection_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = "Выберите AI для генерации изображения:"
    keyboard = [
        [InlineKeyboardButton("🤖 GPT (DALL-E 3)", callback_data=f"select_image_gen_{IMAGE_GEN_DALL_E_3}")],
        [InlineKeyboardButton("🎨 YandexArt", callback_data=f"select_image_gen_{IMAGE_GEN_YANDEXART}")],
        [InlineKeyboardButton("⬅️ Назад", callback_data="select_mode_image")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.callback_query.edit_message_text(text, reply_markup=reply_markup)

async def prompt_for_image_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['state'] = STATE_WAITING_FOR_IMAGE_PROMPT
    
    text = "🖼️ <b>Режим генерации изображений</b>\n\nЧто нарисовать? Отправьте мне подробное текстовое описание."
    
    keyboard = [[InlineKeyboardButton("⬅️ Назад", callback_data="image_gen_create")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    query = update.callback_query
    
    if query and query.message and query.message.text:
        try:
            await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='HTML')
        except BadRequest as e:
            if "Message is not modified" in str(e): await query.answer()
            else: raise
    else:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=text,
            reply_markup=reply_markup,
            parse_mode='HTML'
        )

async def set_ai_provider(telegram_id: int, provider: str):
    await db.db_request("UPDATE users SET current_ai_provider = ? WHERE telegram_id = ?", (provider, telegram_id))

async def handle_ai_selection_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    query = update.callback_query
    if not query: return False

    if query.data == "image_create_new":
        await query.answer()
        await prompt_for_image_text(update, context)
        return True

    if query.data == "image_redraw":
        await query.answer("Перерисовываю...")
        
        prompt_text = context.user_data.get(LAST_IMAGE_PROMPT_KEY)
        if not prompt_text:
            await query.message.reply_text("😔 Не удалось найти последний запрос для перерисовки. Пожалуйста, создайте новое изображение.")
            return True

        image_gen_provider = context.user_data.get(CURRENT_IMAGE_GEN_PROVIDER_KEY)
        
        reply_keyboard = [[
            InlineKeyboardButton("🔄 Перерисовать", callback_data="image_redraw"),
            InlineKeyboardButton("✨ Создать новое", callback_data="image_create_new")
        ]]
        reply_markup = InlineKeyboardMarkup(reply_keyboard)
        
        # [Dev-Ассистент]: Используем <code> для промпта и parse_mode='HTML'
        safe_prompt = html.escape(prompt_text)
        caption_text = f"✨ Ваше изображение по запросу:\n\n<code>{safe_prompt}</code>"

        if image_gen_provider == IMAGE_GEN_YANDEXART:
            await query.message.reply_text(f"🎨 Повторяю запрос в YandexArt:\n\n<code>{safe_prompt}</code>", parse_mode='HTML')
            # ... (остальная логика YandexArt)
            await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.UPLOAD_PHOTO)
            try:
                yandex_client = YandexArtClient(folder_id=os.getenv("YANDEX_FOLDER_ID"), api_key=os.getenv("YANDEX_API_KEY"))
                image_bytes, error_message = await yandex_client.generate_image(prompt_text)
                if error_message: await query.message.reply_text(f"😔 Ошибка при перерисовке: {error_message}")
                elif image_bytes: await query.message.reply_photo(photo=image_bytes, caption=caption_text, parse_mode='HTML', reply_markup=reply_markup)
                else: await query.message.reply_text("Произошла неизвестная ошибка, картинка не была получена.")
            except Exception as e:
                logging.error(f"Критическая ошибка при перерисовке YandexArt: {e}", exc_info=True)
                await query.message.reply_text(f"Произошла критическая ошибка: {e}")

        elif image_gen_provider == IMAGE_GEN_DALL_E_3:
            await query.message.reply_text(f"🎨 Повторяю запрос в DALL-E 3:\n\n<code>{safe_prompt}</code>", parse_mode='HTML')
            # ... (остальная логика DALL-E)
            await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.UPLOAD_PHOTO)
            try:
                caps = get_ai_client_with_caps(GPT_1, system_instruction="You are an image generation assistant.")
                image_url, error_message = await caps.client.generate_image(prompt_text)
                if error_message: await query.message.reply_text(f"😔 Ошибка при перерисовке: {error_message}")
                elif image_url: await query.message.reply_photo(photo=image_url, caption=caption_text, parse_mode='HTML', reply_markup=reply_markup)
                else: await query.message.reply_text("Произошла неизвестная ошибка, картинка не была получена.")
            except Exception as e:
                logging.error(f"Критическая ошибка при перерисовке DALL-E 3: {e}", exc_info=True)
                await query.message.reply_text(f"Произошла критическая ошибка: {e}")
        
        else:
            await query.message.reply_text("😔 Ошибка: не удалось определить, какой генератор использовать для перерисовки.")

        return True

    if query.data == "image_gen_cancel":
        context.user_data['state'] = STATE_NONE
        await query.answer("Операция отменена")
        await show_image_ai_selection_menu(update, context)
        return True 

    if query.data == "select_mode_text":
        await query.answer()
        await show_text_ai_selection_menu(update, context)
        return True
    
    if query.data == "select_mode_image":
        await query.answer()
        await show_image_ai_selection_menu(update, context)
        return True
        
    if query.data == "back_to_ai_mode_hub":
        await query.answer()
        await show_ai_mode_selection_hub(update, context)
        return True
    
    if query.data == "image_gen_create":
        await query.answer()
        await show_image_generation_ai_selection_menu(update, context)
        return True

    if query.data == "image_edit_wip":
        await query.answer("Эта функция находится в активной разработке.", show_alert=True)
        return True

    if query.data.startswith("select_image_gen_"):
        # ... (логика без изменений)
        image_gen_provider = query.data.replace("select_image_gen_", "")
        provider_names = {IMAGE_GEN_DALL_E_3: "GPT (DALL-E 3)", IMAGE_GEN_YANDEXART: "YandexArt"}
        provider_name = provider_names.get(image_gen_provider, "Неизвестная модель")
        context.user_data[CURRENT_IMAGE_GEN_PROVIDER_KEY] = image_gen_provider
        await query.answer(f"Выбрана модель: {provider_name}")
        await prompt_for_image_text(update, context)
        return True

    if query.data.startswith("select_ai_"):
        new_provider = query.data.replace("select_ai_", "")
        user_id = update.effective_user.id
        
        # [Dev-Ассистент]: Блок с новой, гибкой проверкой доступа
        user_data = await db.get_user_by_telegram_id(user_id)
        user_tier = await get_actual_user_tier(user_data)
        available_providers_for_tier = config.SUBSCRIPTION_TIERS[user_tier]['available_providers']

        if new_provider not in available_providers_for_tier:
            # [Dev-Ассистент]: Умный ответ, если нажали на "замочек"
            await query.answer(f"🔒 Эта модель доступна на тарифах '{config.SUBSCRIPTION_TIERS[TIER_LITE]['name']}' и '{config.SUBSCRIPTION_TIERS[TIER_PRO]['name']}'.", show_alert=True)
            return True

        # [Dev-Ассистент]: Если проверка пройдена, всё как и раньше
        await set_ai_provider(user_id, new_provider)
        
        # Получаем display_name из нашего мастер-списка
        provider_name = "Неизвестная модель"
        for model in config.ALL_TEXT_MODELS_FOR_SELECTION:
            if model['provider_id'] == new_provider:
                provider_name = model['display_name'].replace("(умный, vision)", "").replace("(быстрый, vision)", "").strip()
                break
        
        await query.answer(f"Выбрана модель: {provider_name}")
        try: 
            await show_text_ai_selection_menu(update, context)
        except BadRequest as e:
            if "Message is not modified" not in str(e): 
                # [Dev-Ассистент]: Добавляем логгирование для редких ошибок
                logger.warning(f"Не удалось обновить меню выбора AI: {e}")
                pass
        return True
        
    return False