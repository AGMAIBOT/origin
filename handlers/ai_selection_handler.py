# handlers/ai_selection_handler.py (С АКТИВИРОВАННЫМ YANDEXART)

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.error import BadRequest

import database as db
from constants import (
    TIER_PRO, GEMINI_STANDARD, OPENROUTER_DEEPSEEK, GPT_4_OMNI, GPT_O4_MINI,
    OPENROUTER_GEMINI_2_FLASH, STATE_WAITING_FOR_IMAGE_PROMPT, STATE_NONE,
    IMAGE_GEN_DALL_E_3, IMAGE_GEN_YANDEXART, CURRENT_IMAGE_GEN_PROVIDER_KEY,
    LAST_IMAGE_PROMPT_KEY
)
from ai_clients.yandexart_client import YandexArtClient
from ai_clients.factory import get_ai_client_with_caps
from telegram.constants import ChatAction
import os
import logging

async def show_ai_mode_selection_hub(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает главное меню выбора режима: Текст или Изображения."""
    # [Dev-Ассистент]: Как только он входит в этот "хаб", мы принудительно снимаем
    # [Dev-Ассистент]: с бота любую специфическую "шляпу" (например, фотографа).
    context.user_data['state'] = STATE_NONE

    text = "🤖 *Выберите режим работы AI*\n\nВыберите, что вы хотите делать: общаться с текстовой моделью или генерировать/редактировать изображения."
    keyboard = [
        [InlineKeyboardButton("📝 Текстовые модели", callback_data="select_mode_text")],
        [InlineKeyboardButton("🎨 Генерация изображений", callback_data="select_mode_image")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    if update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
    else:
        await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')

async def show_text_ai_selection_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает меню выбора ТЕКСТОВЫХ моделей AI."""
    user_data = await db.get_user_by_telegram_id(update.effective_user.id)
    # [Dev-Ассистент]: ПРОВЕРКА НА ТАРИФ УДАЛЕНА. Меню теперь будет показываться всем.
    current_provider = user_data.get('current_ai_provider') or GEMINI_STANDARD
    text = (
        "📝 *Выберите текстовую модель ИИ*\n\n"
        "Режим \"Персонажи\" теперь работает со всеми моделями. Вы можете бесшовно переключаться между ними, сохраняя контекст диалога.\n\n"
        "Ваш текущий выбор:"
    )
    keyboard = [
        [InlineKeyboardButton(("✅ " if current_provider == GPT_O4_MINI else "") + "GPT-o4-mini (умный, vision)", callback_data=f"select_ai_{GPT_O4_MINI}")],
        [InlineKeyboardButton(("✅ " if current_provider == GPT_4_OMNI else "") + "GPT-4.1-nano (быстрый, vision)", callback_data=f"select_ai_{GPT_4_OMNI}")],
        [InlineKeyboardButton(("✅ " if current_provider == GEMINI_STANDARD else "") + "Gemini 1.5 Flash (креативный, vision)", callback_data=f"select_ai_{GEMINI_STANDARD}")],
        [InlineKeyboardButton(("✅ " if current_provider == OPENROUTER_DEEPSEEK else "") + "DeepSeek (free OR)", callback_data=f"select_ai_{OPENROUTER_DEEPSEEK}")],
        [InlineKeyboardButton("⬅️ Назад", callback_data="back_to_ai_mode_hub")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.callback_query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')

async def show_image_ai_selection_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает меню-хаб для работы с изображениями (создание/редактирование)."""
    text = "🎨 *Работа с изображениями*\n\nВыберите, что вы хотите сделать:"
    keyboard = [
        [InlineKeyboardButton("✨ Создать новое", callback_data="image_gen_create")],
        [InlineKeyboardButton("✍️ Редактировать (в разработке)", callback_data="image_edit_wip")],
        [InlineKeyboardButton("⬅️ Назад", callback_data="back_to_ai_mode_hub")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.callback_query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')

async def show_image_generation_ai_selection_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает меню выбора AI для генерации изображения."""
    text = "Выберите AI для генерации изображения:"
    keyboard = [
        [InlineKeyboardButton("🤖 GPT (DALL-E 3)", callback_data=f"select_image_gen_{IMAGE_GEN_DALL_E_3}")],
        [InlineKeyboardButton("🎨 YandexArt", callback_data=f"select_image_gen_{IMAGE_GEN_YANDEXART}")],
        [InlineKeyboardButton("⬅️ Назад", callback_data="select_mode_image")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.callback_query.edit_message_text(text, reply_markup=reply_markup)

async def prompt_for_image_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Переводит бота в режим ожидания промпта для генерации изображения.
    [Dev-Ассистент]: Теперь эта функция умная: она либо редактирует существующее
    [Dev-Ассистент]: текстовое сообщение, либо отправляет новое, если вызвана из-под фото.
    """
    context.user_data['state'] = STATE_WAITING_FOR_IMAGE_PROMPT
    
    text = "🖼️ *Режим генерации изображений*\n\nЧто нарисовать? Отправьте мне подробное текстовое описание."
    
    # [Dev-Ассистент]: Здесь мы используем ту же кнопку "Отмена", что и в других местах.
    # [Dev-Ассистент]: Но теперь она ведет в меню выбора генераторов, что логично.
    keyboard = [
        [InlineKeyboardButton("⬅️ Назад", callback_data="image_gen_create")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    query = update.callback_query
    
    # [Dev-Ассистент]: НАЧАЛО НОВОЙ ЛОГИКИ
    # [Dev-Ассистент]: Проверяем, есть ли у сообщения, с которого пришел callback, текстовое поле.
    # [Dev-Ассистент]: Сообщения с фото его не имеют, поэтому эта проверка вернет False.
    if query and query.message and query.message.text:
        # [Dev-Ассистент]: Сценарий 1: Мы пришли из текстового меню. Редактируем сообщение.
        try:
            await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
        except BadRequest as e:
            if "Message is not modified" in str(e):
                await query.answer() # Просто отвечаем на колбэк, если текст не изменился
            else:
                raise # Перебрасываем другие ошибки
    else:
        # [Dev-Ассистент]: Сценарий 2: Мы пришли из-под фото. Отправляем новое сообщение.
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=text,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )


async def set_ai_provider(telegram_id: int, provider: str):
    """Обновляет AI провайдера для пользователя в БД."""
    await db.db_request("UPDATE users SET current_ai_provider = ? WHERE telegram_id = ?", (provider, telegram_id))


async def handle_ai_selection_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Обрабатывает навигацию по меню выбора AI и выбор конкретной модели."""
    query = update.callback_query
    if not query: return False

    if query.data == "image_create_new":
        await query.answer()
        await prompt_for_image_text(update, context)
        return True

    # [Dev-Ассистент]: НАЧАЛО БОЛЬШИХ ИЗМЕНЕНИЙ В БЛОКЕ "ПЕРЕРИСОВАТЬ"
    if query.data == "image_redraw":
        await query.answer("Перерисовываю...")
        
        prompt_text = context.user_data.get(LAST_IMAGE_PROMPT_KEY)
        if not prompt_text:
            await query.message.reply_text("😔 Не удалось найти последний запрос для перерисовки. Пожалуйста, создайте новое изображение.")
            return True

        # [Dev-Ассистент]: 1. Определяем, какой генератор был использован последним.
        image_gen_provider = context.user_data.get(CURRENT_IMAGE_GEN_PROVIDER_KEY)
        
        # [Dev-Ассистент]: 2. Создаем универсальную клавиатуру.
        reply_keyboard = [
            [
                InlineKeyboardButton("🔄 Перерисовать", callback_data="image_redraw"),
                InlineKeyboardButton("✨ Создать новое", callback_data="image_create_new")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(reply_keyboard)

        # [Dev-Ассистент]: 3. В зависимости от провайдера, выполняем нужную логику.
        # --- Маршрут для YandexArt ---
        if image_gen_provider == IMAGE_GEN_YANDEXART:
            await query.message.reply_text(f"🎨 Повторяю запрос в YandexArt:\n\n`{prompt_text}`", parse_mode='Markdown')
            await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.UPLOAD_PHOTO)
            try:
                yandex_client = YandexArtClient(folder_id=os.getenv("YANDEX_FOLDER_ID"), api_key=os.getenv("YANDEX_API_KEY"))
                image_bytes, error_message = await yandex_client.generate_image(prompt_text)
                if error_message:
                    await query.message.reply_text(f"😔 Ошибка при перерисовке: {error_message}")
                elif image_bytes:
                    await query.message.reply_photo(photo=image_bytes, caption=f"✨ Ваше изображение от YandexArt по запросу:\n\n`{prompt_text}`", parse_mode='Markdown', reply_markup=reply_markup)
                else:
                    await query.message.reply_text("Произошла неизвестная ошибка, картинка не была получена.")
            except Exception as e:
                logging.error(f"Критическая ошибка при перерисовке YandexArt: {e}", exc_info=True)
                await query.message.reply_text(f"Произошла критическая ошибка: {e}")

        # --- Маршрут для DALL-E 3 (GPT) ---
        elif image_gen_provider == IMAGE_GEN_DALL_E_3:
            await query.message.reply_text(f"🎨 Повторяю запрос в DALL-E 3:\n\n`{prompt_text}`", parse_mode='Markdown')
            await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.UPLOAD_PHOTO)
            try:
                caps = get_ai_client_with_caps(GPT_4_OMNI, system_instruction="You are an image generation assistant.")
                image_url, error_message = await caps.client.generate_image(prompt_text)
                if error_message:
                    await query.message.reply_text(f"😔 Ошибка при перерисовке: {error_message}")
                elif image_url:
                    await query.message.reply_photo(photo=image_url, caption=f"✨ Ваше изображение по запросу:\n\n`{prompt_text}`", parse_mode='Markdown', reply_markup=reply_markup)
                else:
                    await query.message.reply_text("Произошла неизвестная ошибка, картинка не была получена.")
            except Exception as e:
                logging.error(f"Критическая ошибка при перерисовке DALL-E 3: {e}", exc_info=True)
                await query.message.reply_text(f"Произошла критическая ошибка: {e}")
        
        else:
            await query.message.reply_text("😔 Ошибка: не удалось определить, какой генератор использовать для перерисовки.")

        return True

    # --- Старая логика ---
    if query.data == "image_gen_cancel":
        context.user_data['state'] = STATE_NONE
        await query.answer("Операция отменена")
        await show_image_ai_selection_menu(update, context)
        return True 

    # ... остальная часть функции без изменений ...
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
        image_gen_provider = query.data.replace("select_image_gen_", "")
        
        provider_names = {
            IMAGE_GEN_DALL_E_3: "GPT (DALL-E 3)",
            IMAGE_GEN_YANDEXART: "YandexArt"
        }
        provider_name = provider_names.get(image_gen_provider, "Неизвестная модель")

        context.user_data[CURRENT_IMAGE_GEN_PROVIDER_KEY] = image_gen_provider
        
        await query.answer(f"Выбрана модель: {provider_name}")
        await prompt_for_image_text(update, context)
        return True

    if query.data.startswith("select_ai_"):
        user_data = await db.get_user_by_telegram_id(update.effective_user.id)
        if not user_data or user_data.get('subscription_tier') != TIER_PRO:
            await query.answer("Эта функция доступна только на Pro-тарифе.", show_alert=True)
            return True 

        new_provider = query.data.replace("select_ai_", "")
        user_id = update.effective_user.id
        await set_ai_provider(user_id, new_provider)
        provider_names = {
            GEMINI_STANDARD: "Gemini 1.5 Flash",
            OPENROUTER_DEEPSEEK: "DeepSeek (OpenRouter)",
            GPT_4_OMNI: "GPT-4.1 nano",
            GPT_O4_MINI: "GPT-o4-mini",
            OPENROUTER_GEMINI_2_FLASH: "Gemini 2.0 Flash (экспериментальный)"
        }
        provider_name = provider_names.get(new_provider, "Неизвестная модель")
        await query.answer(f"Выбрана модель: {provider_name}")
        try:
            await show_text_ai_selection_menu(update, context)
        except BadRequest as e:
            if "Message is not modified" not in str(e):
                pass
        return True
        
    return False