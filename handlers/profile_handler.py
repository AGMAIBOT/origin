# handlers/profile_handler.py (ПОЛНАЯ НОВАЯ ВЕРСИЯ С ЗАЩИТОЙ)

import logging
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.helpers import escape_markdown
from telegram.error import BadRequest

import config
from constants import TIER_FREE
from utils import get_actual_user_tier, require_verification # <<< Импортируем декоратор
import database as db

logger = logging.getLogger(__name__)

# <<< Применяем декоратор здесь
@require_verification
async def show_profile(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # ... весь остальной код функции show_profile без изменений ...
    user_id = await db.add_or_update_user(telegram_id=update.effective_user.id, full_name=update.effective_user.full_name, username=update.effective_user.username)
    if not user_id:
        if update.callback_query: await update.callback_query.answer("Не удалось получить данные вашего профиля.", show_alert=True)
        else: await update.message.reply_text("Не удалось получить данные вашего профиля.")
        return
    user_data = await db.get_user_by_id(user_id)
    if not user_data:
        if update.callback_query: await update.callback_query.answer("Не удалось найти ваш профиль в базе данных.", show_alert=True)
        else: await update.message.reply_text("Не удалось найти ваш профиль в базе данных.")
        return
    current_tier_name = await get_actual_user_tier(user_data)
    tier_params = config.SUBSCRIPTION_TIERS[current_tier_name]
    user_name = escape_markdown(user_data.get('full_name', 'N/A'), version=2)
    user_tg_id = user_data.get('telegram_id', 'N/A')
    tier_display_name = escape_markdown(tier_params['name'], version=2)
    limit_info = ""
    if tier_params['daily_limit'] is not None:
        requests_made = user_data.get('daily_requests_count', 0)
        requests_limit = tier_params['daily_limit']
        progress = int((requests_made / requests_limit) * 10)
        progress_bar = '🟩' * progress + '⬜️' * (10 - progress)
        limit_info = (f"📊 *Использование сегодня:*\n`{requests_made} / {requests_limit}` запросов\n{progress_bar}\n")
    else:
        limit_info = "📊 *Использование сегодня:* Безлимитно\n"
    expiry_info = ""
    if current_tier_name != TIER_FREE and user_data.get('subscription_expiry_date'):
        expiry_date_str = user_data.get('subscription_expiry_date')
        expiry_date = datetime.fromisoformat(expiry_date_str) if isinstance(expiry_date_str, str) else expiry_date_str
        if expiry_date: expiry_info = f"🗓️ *Подписка активна до:* {expiry_date.strftime('%d\\.%m\\.%Y %H:%M')}\n"
    text = (f"👤 *Ваш Профиль*\n\n🏷️ *Имя:* {user_name}\n🆔 *Telegram ID:* `{user_tg_id}`\n\n⭐ *Тарифный план:* *{tier_display_name}*\n{expiry_info}\n{limit_info}_Счетчик сбрасывается ежедневно в 00:00 UTC\\._")
    keyboard = [[InlineKeyboardButton("🔄 Обновить", callback_data="refresh_profile")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    if update.callback_query:
        try:
            await update.callback_query.edit_message_text(text, reply_markup=reply_markup, parse_mode='MarkdownV2')
        except BadRequest as e:
            if "Message is not modified" in str(e): await update.callback_query.answer(text="Изменений нет.")
            else:
                logger.error(f"Ошибка при обновлении профиля: {e}", exc_info=True)
                await update.callback_query.answer("Произошла ошибка при обновлении.", show_alert=True)
    else:
        await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='MarkdownV2')

# <<< Применяем декоратор и здесь
@require_verification
async def handle_profile_callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    query = update.callback_query
    if not query: return False
    if query.data == "refresh_profile":
        await show_profile(update, context)
        return True
    return False