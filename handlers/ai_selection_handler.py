# handlers/ai_selection_handler.py

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

import database as db
from constants import TIER_PRO, GEMINI_STANDARD, OPENROUTER_DEEPSEEK, GPT_4_OMNI

async def show_ai_selection_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает меню выбора AI только для Pro подписчиков."""
    user_data = await db.get_user_by_telegram_id(update.effective_user.id)
    
    # Проверка, что у пользователя есть Pro-тариф
    if not user_data or user_data.get('subscription_tier') != TIER_PRO:
        await update.message.reply_text("Функция выбора AI доступна только на Pro-тарифе.")
        return
        
    current_provider = user_data.get('current_ai_provider') or GEMINI_STANDARD

    text = (
        "🤖 *Выберите модель ИИ*\n\n"
        "При выборе `DeepSeek` или `GPT` режим \"Персонажи\" будет временно отключен. "
        "Бот будет вести с вами обычный диалог.\n\n"
        "Ваш текущий выбор:"
    )
    
    keyboard = [
        [
            InlineKeyboardButton(
                ("✅ " if current_provider == GEMINI_STANDARD else "") + "Gemini (креативный, vision)",
                callback_data=f"select_ai_{GEMINI_STANDARD}"
            )
        ],
        [
            InlineKeyboardButton(
                ("✅ " if current_provider == OPENROUTER_DEEPSEEK else "") + "DeepSeek (через OpenRouter)",
                callback_data=f"select_ai_{OPENROUTER_DEEPSEEK}"
            )
        ],
        [
            InlineKeyboardButton(
                ("✅ " if current_provider == GPT_4_OMNI else "") + "GPT-4 Omni (мощный)",
                callback_data=f"select_ai_{GPT_4_OMNI}"
            )
        ]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')


async def set_ai_provider(telegram_id: int, provider: str):
    """Обновляет AI провайдера для пользователя в БД."""
    await db.db_request("UPDATE users SET current_ai_provider = ? WHERE telegram_id = ?", (provider, telegram_id))


async def handle_ai_selection_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Обрабатывает выбор AI из инлайн-меню."""
    query = update.callback_query
    if not query or not query.data.startswith("select_ai_"):
        return False
        
    new_provider = query.data.replace("select_ai_", "")
    user_id = update.effective_user.id
    
    await set_ai_provider(user_id, new_provider)
    
    provider_names = {
        GEMINI_STANDARD: "Gemini",
        OPENROUTER_DEEPSEEK: "DeepSeek (OpenRouter)",
        GPT_4_OMNI: "GPT-4 Omni"
    }
    provider_name = provider_names.get(new_provider, "Неизвестная модель")
    
    await query.answer(f"Выбрана модель: {provider_name}")
    
    # Обновляем сообщение с меню, чтобы галочка передвинулась
    user_data = await db.get_user_by_telegram_id(user_id)
    current_provider = user_data.get('current_ai_provider')
    
    keyboard = [
        [
            InlineKeyboardButton(
                ("✅ " if current_provider == GEMINI_STANDARD else "") + "Gemini (креативный, vision)",
                callback_data=f"select_ai_{GEMINI_STANDARD}"
            )
        ],
        [
            InlineKeyboardButton(
                ("✅ " if current_provider == OPENROUTER_DEEPSEEK else "") + "DeepSeek (через OpenRouter)",
                callback_data=f"select_ai_{OPENROUTER_DEEPSEEK}"
            )
        ],
        [
            InlineKeyboardButton(
                ("✅ " if current_provider == GPT_4_OMNI else "") + "GPT-4 Omni (мощный)",
                callback_data=f"select_ai_{GPT_4_OMNI}"
            )
        ]
    ]
    await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(keyboard))

    return True