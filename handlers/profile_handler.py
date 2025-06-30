# handlers/profile_handler.py (ОБНОВЛЕННАЯ ВЕРСИЯ С КОШЕЛЬКОМ И РЕФЕРАЛКОЙ)

import logging
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.error import BadRequest
import html
import config
from constants import * 
from utils import get_actual_user_tier, require_verification
import database as db

logger = logging.getLogger(__name__)

@require_verification
async def show_profile_hub(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = await db.add_or_update_user(telegram_id=update.effective_user.id, full_name=update.effective_user.full_name, username=update.effective_user.username)
    user_data = await db.get_user_by_id(user_id)
    if not user_data:
        return

    current_tier_name = await get_actual_user_tier(user_data)
    tier_params = config.SUBSCRIPTION_TIERS[current_tier_name]
    
    user_name = html.escape(user_data.get('full_name', 'N/A'))
    user_tg_id = user_data.get('telegram_id', 'N/A')
    tier_display_name = html.escape(tier_params['name'])
    
    limit_info = ""
    if tier_params['daily_limit'] is not None:
        requests_made = user_data.get('daily_requests_count', 0)
        requests_limit = tier_params['daily_limit']
        progress = int((requests_made / requests_limit) * 10)
        progress_bar = '🟩' * progress + '⬜️' * (10 - progress)
        limit_info = (f"📊 <b>Использование сегодня:</b>\n<code>{requests_made} / {requests_limit}</code> запросов\n{progress_bar}\n")
    else:
        limit_info = "📊 <b>Использование сегодня:</b> Безлимитно\n"
    
    expiry_info = ""
    if current_tier_name != TIER_FREE and user_data.get('subscription_expiry_date'):
        expiry_date_str = user_data.get('subscription_expiry_date')
        expiry_date = datetime.fromisoformat(expiry_date_str) if isinstance(expiry_date_str, str) else expiry_date_str
        if expiry_date: expiry_info = f"🗓️ <b>Подписка активна до:</b> {expiry_date.strftime('%d.%m.%Y %H:%M')}\n"
    
    user_balance = user_data.get('balance', 0)
    balance_info = f"💰 <b>Баланс AGMcoin:</b> <code>{user_balance}</code>\n"

    text = (f"👤 <b>Ваш Профиль</b>\n\n"
            f"🏷️ <b>Имя:</b> {user_name}\n"
            f"🆔 <b>Telegram ID:</b> <code>{user_tg_id}</code>\n\n"
            f"{balance_info}\n"
            f"⭐ <b>Тарифный план:</b> <i>{tier_display_name}</i>\n"
            f"{expiry_info}\n"
            f"{limit_info}"
            f"<i>Счетчик запросов сбрасывается ежедневно в 00:00 UTC</i>")

    keyboard = [
        [
            InlineKeyboardButton("👛 Кошелек", callback_data=WALLET_HUB), 
            InlineKeyboardButton("🛒 Магазин (в разработке)", callback_data=PROFILE_HUB_SHOP)
        ],
        [InlineKeyboardButton("🛠️ Настройки", callback_data=PROFILE_HUB_SETTINGS)],
        [InlineKeyboardButton("🔄 Обновить", callback_data="refresh_profile")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    if update.callback_query:
        try:
            await update.callback_query.edit_message_text(text, reply_markup=reply_markup, parse_mode='HTML')
        except BadRequest as e:
            if "Message is not modified" in str(e): await update.callback_query.answer()
            else: raise
    else:
        await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='HTML')

async def show_wallet_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    user_id = await db.add_or_update_user(telegram_id=update.effective_user.id, full_name=update.effective_user.full_name, username=update.effective_user.username)
    user_data = await db.get_user_by_id(user_id)
    if not user_data:
        await query.edit_message_text("Ошибка: не удалось загрузить данные пользователя.")
        return
    
    user_balance = user_data.get('balance', 0)
    
    text = (
        f"👛 <b>Ваш Кошелек</b>\n\n"
        f"✨ <b>Баланс AGMcoin:</b> <code>{user_balance}</code>\n\n"
        f"Используйте AGMcoin для оплаты дополнительных функций и повышения лимитов."
    )

    keyboard = [
        [InlineKeyboardButton("➕ Пополнить", callback_data=WALLET_TOPUP_START)],
        [InlineKeyboardButton("🤝 Реферальная программа", callback_data=WALLET_REFERRAL_PROGRAM)],
        [InlineKeyboardButton("⬅️ Назад", callback_data=WALLET_BACK_TO_PROFILE)]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    try:
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='HTML')
    except BadRequest as e:
        if "Message is not modified" in str(e): await query.answer()
        else: raise

async def handle_topup_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.callback_query.answer("Раздел пополнения в разработке. Скоро здесь появятся способы оплаты!", show_alert=True)

# [Dev-Ассистент]: НОВАЯ ФУНКЦИЯ: Показать меню Реферальной программы
async def show_referral_program_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    user_id = await db.add_or_update_user(telegram_id=update.effective_user.id, full_name=update.effective_user.full_name, username=update.effective_user.username)
    user_data = await db.get_user_by_id(user_id)
    if not user_data:
        await query.edit_message_text("Ошибка: не удалось загрузить данные пользователя.")
        return
    
    user_telegram_id = user_data['telegram_id'] # Нужен для генерации ссылки
    
    # [Dev-Ассистент]: Получаем данные о рефералах
    referrals = await db.get_user_referrals(user_id)
    referral_earnings = await db.get_user_referral_earnings(user_id)

    # [Dev-Ассистент]: Генерируем уникальную реферальную ссылку
    bot_info = await context.bot.get_me()
    referral_link = f"https://t.me/{bot_info.username}?start=ref_{user_telegram_id}"
    
    # [Dev-Ассистент]: Формируем текст сообщения
    text = (
        f"🤝 <b>Реферальная программа</b>\n\n"
        f"Приглашайте друзей в бот и зарабатывайте {config.REFERRAL_PERCENTAGE}% от каждого их пополнения!\n\n"
        f"🔗 <b>Ваша реферальная ссылка:</b>\n"
        f"<code>{html.escape(referral_link)}</code>\n\n" # Обязательно экранируем ссылку
        f"📊 <b>Статистика:</b>\n"
        f"Приглашено активных пользователей: <b>{len(referrals)}</b>\n"
        f"Заработано по рефералам: <b>{referral_earnings} AGMcoin</b>\n\n"
        f"<i>Приглашенные пользователи должны пройти верификацию и запустить бота по вашей ссылке. Бонус начисляется с каждого пополнения, совершенного вашими рефералами.</i>"
    )

    keyboard = [
        [InlineKeyboardButton("⬅️ Назад", callback_data=WALLET_HUB)] # Возвращаемся в меню Кошелька
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    try:
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='HTML')
    except BadRequest as e:
        if "Message is not modified" in str(e): await query.answer()
        else: raise


async def show_settings_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    
    text = "🛠️ <b>Настройки</b>\n\nЗдесь вы можете изменить, как бот взаимодействует с вами."
    
    keyboard = [
        [InlineKeyboardButton("📝 Формат ответа", callback_data=SETTINGS_OUTPUT_FORMAT)],
        [InlineKeyboardButton("⬅️ Назад в профиль", callback_data="back_to_profile_hub")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='HTML')


async def show_format_selection_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    user_data = await db.get_user_by_telegram_id(update.effective_user.id)
    current_format = user_data.get('output_format', OUTPUT_FORMAT_TEXT)

    text = "📝 <b>Формат ответа</b>\n\nВыберите, в каком виде вы хотите получать ответы от AI:"
    
    keyboard = [
        [InlineKeyboardButton(
            ("✅ " if current_format == OUTPUT_FORMAT_TEXT else "") + "Текст в чате", 
            callback_data=FORMAT_SET_TEXT
        )],
        [InlineKeyboardButton(
            ("✅ " if current_format == OUTPUT_FORMAT_TXT else "") + "Файл .txt",
            callback_data=FORMAT_SET_TXT
        )],
        [InlineKeyboardButton(
            ("✅ " if current_format == OUTPUT_FORMAT_PDF else "") + "Файл .pdf", 
            callback_data=FORMAT_SET_PDF
        )],
        [InlineKeyboardButton("⬅️ Назад в настройки", callback_data=SETTINGS_BACK_TO_PROFILE_HUB)]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='HTML')


async def set_output_format(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    format_map = {
        FORMAT_SET_TEXT: OUTPUT_FORMAT_TEXT,
        FORMAT_SET_TXT: OUTPUT_FORMAT_TXT,
        FORMAT_SET_PDF: OUTPUT_FORMAT_PDF,
    }
    new_format = format_map.get(query.data)
    
    user = await db.get_user_by_telegram_id(update.effective_user.id)
    if not user:
        await query.answer("Произошла ошибка, ваш профиль не найден.", show_alert=True)
        return
        
    await db.set_user_output_format(user_id=user['id'], output_format=new_format)
    await query.answer(f"Формат изменен на '{new_format}'")
    
    await show_format_selection_menu(update, context)

async def handle_profile_callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    query = update.callback_query
    if not query: return False
    
    routes = {
        "refresh_profile": show_profile_hub,
        "back_to_profile_hub": show_profile_hub,
        PROFILE_HUB_SETTINGS: show_settings_menu,
        SETTINGS_BACK_TO_PROFILE_HUB: show_settings_menu,
        SETTINGS_OUTPUT_FORMAT: show_format_selection_menu,
        FORMAT_BACK_TO_SETTINGS: show_settings_menu,
        FORMAT_SET_TEXT: set_output_format,
        FORMAT_SET_TXT: set_output_format,
        FORMAT_SET_PDF: set_output_format,
        
        WALLET_HUB: show_wallet_menu,
        WALLET_TOPUP_START: handle_topup_start,
        WALLET_REFERRAL_PROGRAM: show_referral_program_menu, # <<< [Dev-Ассистент]: Теперь ведет на новую функцию
        WALLET_BACK_TO_PROFILE: show_profile_hub, 
    }

    if query.data in [PROFILE_HUB_SHOP]:
        await query.answer("Этот раздел находится в разработке.", show_alert=True)
        return True

    handler = routes.get(query.data)
    if handler:
        await handler(update, context)
        return True
        
    return False