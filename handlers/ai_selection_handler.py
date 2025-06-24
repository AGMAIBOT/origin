# handlers/ai_selection_handler.py

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.error import BadRequest

import database as db
from constants import TIER_PRO, GEMINI_STANDARD, OPENROUTER_DEEPSEEK, GPT_4_OMNI, OPENROUTER_GEMINI_2_FLASH

# <<< НОВАЯ ФУНКЦИЯ: Показывает главный хаб выбора режима AI >>>
async def show_ai_mode_selection_hub(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает главное меню выбора режима: Текст или Изображения."""
    text = "🤖 *Выберите режим работы AI*\n\nВыберите, что вы хотите делать: общаться с текстовой моделью или генерировать изображения."
    
    keyboard = [
        [InlineKeyboardButton("📝 Текстовые модели", callback_data="select_mode_text")],
        [InlineKeyboardButton("🎨 Генерация изображений", callback_data="select_mode_image")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    # Определяем, нужно ли отправлять новое сообщение или редактировать старое
    if update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
    else:
        await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')

# <<< ИЗМЕНЕНИЕ: Старая функция, переименована и адаптирована >>>
async def show_text_ai_selection_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает меню выбора ТЕКСТОВЫХ моделей AI."""
    user_data = await db.get_user_by_telegram_id(update.effective_user.id)
    if not user_data or user_data.get('subscription_tier') != TIER_PRO:
        await update.callback_query.answer("Эта функция доступна только на Pro-тарифе.", show_alert=True)
        return
        
    current_provider = user_data.get('current_ai_provider') or GEMINI_STANDARD

    # <<< ИЗМЕНЕНИЕ: Текст обновлен, т.к. персонажи теперь работают со всеми AI >>>
    text = (
        "📝 *Выберите текстовую модель ИИ*\n\n"
        "Режим \"Персонажи\" теперь работает со всеми моделями. Вы можете бесшовно переключаться между ними, сохраняя контекст диалога.\n\n"
        "Ваш текущий выбор:"
    )
    
    keyboard = [
        [InlineKeyboardButton(("✅ " if current_provider == GPT_4_OMNI else "") + "GPT-4 Omni (мощный)", callback_data=f"select_ai_{GPT_4_OMNI}")],
        [InlineKeyboardButton(("✅ " if current_provider == GEMINI_STANDARD else "") + "Gemini (креативный, vision)", callback_data=f"select_ai_{GEMINI_STANDARD}")],
        [InlineKeyboardButton(("✅ " if current_provider == OPENROUTER_GEMINI_2_FLASH else "") + "Gemini 2.0 Flash (экспериментальный)", callback_data=f"select_ai_{OPENROUTER_GEMINI_2_FLASH}")],
        [InlineKeyboardButton(("✅ " if current_provider == OPENROUTER_DEEPSEEK else "") + "DeepSeek (через OpenRouter)", callback_data=f"select_ai_{OPENROUTER_DEEPSEEK}")],
        [InlineKeyboardButton("⬅️ Назад", callback_data="back_to_ai_mode_hub")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.callback_query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')

# <<< НОВАЯ ФУНКЦИЯ: Меню-заглушка для генерации изображений >>>
async def show_image_ai_selection_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает меню-заглушку для выбора моделей генерации изображений."""
    text = "🎨 *Генерация изображений*\n\nЭтот раздел находится в разработке. Скоро здесь можно будет выбрать модели, такие как DALL·E 3."
    keyboard = [
        [InlineKeyboardButton("⬅️ Назад", callback_data="back_to_ai_mode_hub")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.callback_query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')


async def set_ai_provider(telegram_id: int, provider: str):
    """Обновляет AI провайдера для пользователя в БД."""
    await db.db_request("UPDATE users SET current_ai_provider = ? WHERE telegram_id = ?", (provider, telegram_id))

# <<< ИЗМЕНЕНИЕ: Главный обработчик колбэков переписан для новой логики >>>
async def handle_ai_selection_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Обрабатывает навигацию по меню выбора AI и выбор конкретной модели."""
    query = update.callback_query
    if not query: return False

    # --- Маршрутизация по меню ---
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

    # --- Обработка выбора конкретной ТЕКСТОВОЙ модели ---
    if query.data.startswith("select_ai_"):
        new_provider = query.data.replace("select_ai_", "")
        user_id = update.effective_user.id
        
        await set_ai_provider(user_id, new_provider)
        
        provider_names = {
            GEMINI_STANDARD: "Gemini 1.5 Flash",
            OPENROUTER_DEEPSEEK: "DeepSeek (OpenRouter)",
            GPT_4_OMNI: "GPT-4 Omni",
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