# handlers/ai_selection_handler.py

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.error import BadRequest

import database as db
# <<< ИЗМЕНЕНИЕ: Импортируем наши новые константы >>>
from constants import (
    TIER_PRO, GEMINI_STANDARD, OPENROUTER_DEEPSEEK, GPT_4_OMNI, 
    OPENROUTER_GEMINI_2_FLASH, STATE_WAITING_FOR_IMAGE_PROMPT, STATE_NONE,
    IMAGE_GEN_DALL_E_3, IMAGE_GEN_YANDEXART, CURRENT_IMAGE_GEN_PROVIDER_KEY
)

async def show_ai_mode_selection_hub(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает главное меню выбора режима: Текст или Изображения."""
    text = "🤖 *Выберите режим работы AI*\n\nВыберите, что вы хотите делать: общаться с текстовой моделью или генерировать/редактировать изображения."
    keyboard = [
        [InlineKeyboardButton("📝 Текстовые модели", callback_data="select_mode_text")],
        [InlineKeyboardButton("🎨 Генерация изображений", callback_data="select_mode_image")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    if update.callback_query:
        context.user_data['state'] = STATE_NONE
        await update.callback_query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
    else:
        await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')

async def show_text_ai_selection_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает меню выбора ТЕКСТОВЫХ моделей AI."""
    # (Эта функция без изменений)
    user_data = await db.get_user_by_telegram_id(update.effective_user.id)
    if not user_data or user_data.get('subscription_tier') != TIER_PRO:
        await update.callback_query.answer("Эта функция доступна только на Pro-тарифе.", show_alert=True)
        return
    current_provider = user_data.get('current_ai_provider') or GEMINI_STANDARD
    text = (
        "📝 *Выберите текстовую модель ИИ*\n\n"
        "Режим \"Персонажи\" теперь работает со всеми моделями. Вы можете бесшовно переключаться между ними, сохраняя контекст диалога.\n\n"
        "Ваш текущий выбор:"
    )
    keyboard = [
        [InlineKeyboardButton(("✅ " if current_provider == GPT_4_OMNI else "") + "GPT-4.1 nano (быстрый, vision)", callback_data=f"select_ai_{GPT_4_OMNI}")],
        [InlineKeyboardButton(("✅ " if current_provider == GEMINI_STANDARD else "") + "Gemini 1.5 Flash (креативный, vision)", callback_data=f"select_ai_{GEMINI_STANDARD}")],
        [InlineKeyboardButton(("✅ " if current_provider == OPENROUTER_DEEPSEEK else "") + "DeepSeek (free OR)", callback_data=f"select_ai_{OPENROUTER_DEEPSEEK}")],
        [InlineKeyboardButton("⬅️ Назад", callback_data="back_to_ai_mode_hub")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.callback_query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')

async def show_image_ai_selection_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает меню-хаб для работы с изображениями (создание/редактирование)."""
    # (Эта функция без изменений)
    text = "🎨 *Работа с изображениями*\n\nВыберите, что вы хотите сделать:"
    keyboard = [
        [InlineKeyboardButton("✨ Создать новое", callback_data="image_gen_create")],
        [InlineKeyboardButton("✍️ Редактировать (в разработке)", callback_data="image_edit_wip")],
        [InlineKeyboardButton("⬅️ Назад", callback_data="back_to_ai_mode_hub")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.callback_query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')


# <<< ИЗМЕНЕНИЕ: Новая функция для показа меню выбора AI для генерации >>>
async def show_image_generation_ai_selection_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает меню выбора AI для генерации изображения."""
    text = "Выберите AI для генерации изображения:"
    keyboard = [
        [InlineKeyboardButton("🤖 GPT (DALL-E 3)", callback_data=f"select_image_gen_{IMAGE_GEN_DALL_E_3}")],
        [InlineKeyboardButton("🎨 YandexArt (в разработке)", callback_data=f"select_image_gen_{IMAGE_GEN_YANDEXART}")],
        [InlineKeyboardButton("⬅️ Назад", callback_data="select_mode_image")] # Возврат в меню "Создать/Редактировать"
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.callback_query.edit_message_text(text, reply_markup=reply_markup)

# <<< ИЗМЕНЕНИЕ: Старая функция `prompt_for_image_generation` переименована и теперь вызывается ПОСЛЕ выбора AI >>>
async def prompt_for_image_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Переводит бота в режим ожидания промпта для генерации изображения."""
    context.user_data['state'] = STATE_WAITING_FOR_IMAGE_PROMPT
    
    text = "🖼️ *Режим генерации изображений*\n\nЧто нарисовать? Отправьте мне подробное текстовое описание."
    keyboard = [
        # Кнопка отмены теперь ведет в меню выбора AI для генерации
        [InlineKeyboardButton("❌ Отмена", callback_data="image_gen_create")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.callback_query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')


async def set_ai_provider(telegram_id: int, provider: str):
    """Обновляет AI провайдера для пользователя в БД."""
    # (Эта функция без изменений)
    await db.db_request("UPDATE users SET current_ai_provider = ? WHERE telegram_id = ?", (provider, telegram_id))


async def handle_ai_selection_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Обрабатывает навигацию по меню выбора AI и выбор конкретной модели."""
    query = update.callback_query
    if not query: return False

    # --- Маршрутизация по главным меню ---
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
    
    # --- Маршрутизация по меню работы с изображениями ---
    if query.data == "image_gen_create":
        await query.answer()
        # <<< ИЗМЕНЕНИЕ: Теперь эта кнопка вызывает новое меню выбора AI >>>
        await show_image_generation_ai_selection_menu(update, context)
        return True

    if query.data == "image_edit_wip":
        await query.answer("Эта функция находится в активной разработке.", show_alert=True)
        return True

    # <<< ИЗМЕНЕНИЕ: Новый обработчик для выбора конкретного AI для ГЕНЕРАЦИИ >>>
    if query.data.startswith("select_image_gen_"):
        image_gen_provider = query.data.replace("select_image_gen_", "")
        
        # Обработка заглушки для YandexArt
        if image_gen_provider == IMAGE_GEN_YANDEXART:
            await query.answer("Генерация через YandexArt пока не доступна.", show_alert=True)
            return True

        # Сохраняем выбор пользователя в user_data
        context.user_data[CURRENT_IMAGE_GEN_PROVIDER_KEY] = image_gen_provider
        
        # Только теперь, после выбора AI, запрашиваем промпт
        await query.answer(f"Выбран GPT (DALL-E 3)")
        await prompt_for_image_text(update, context)
        return True

    # --- Обработка выбора конкретной ТЕКСТОВОЙ модели ---
    if query.data.startswith("select_ai_"):
        # (Этот блок без изменений)
        new_provider = query.data.replace("select_ai_", "")
        user_id = update.effective_user.id
        await set_ai_provider(user_id, new_provider)
        provider_names = {
            GEMINI_STANDARD: "Gemini 1.5 Flash",
            OPENROUTER_DEEPSEEK: "DeepSeek (OpenRouter)",
            GPT_4_OMNI: "GPT-4.1 nano",
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