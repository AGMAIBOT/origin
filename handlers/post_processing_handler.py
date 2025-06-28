# handlers/post_processing_handler.py (НОВЫЙ ФАЙЛ)

import logging
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes

from constants import *
import config

logger = logging.getLogger(__name__)

# [Dev-Ассистент]: Словарь с промптами для разных действий. Легко расширять.
ACTION_PROMPTS = {
    ACTION_SHORTEN: "Резюмируй свой предыдущий ответ.",
    ACTION_EXPAND: "Разверни свой предыдущий ответ.",
    ACTION_REPHRASE: "Перефразируй свой предыдущий ответ."
}

def get_post_processing_keyboard(text_length: int) -> InlineKeyboardMarkup | None:
    """
    [Dev-Ассистент]: В зависимости от длины текста, возвращает нужную клавиатуру или ничего.
    """
    buttons = []
    # Ответ средней длины
    if config.POST_PROCESSING_SHORT_THRESHOLD <= text_length < config.POST_PROCESSING_LONG_THRESHOLD:
        if text_length <= config.POST_PROCESSING_MEDIUM_THRESHOLD:
            buttons.append(InlineKeyboardButton("↔️ Раскрой мысль", callback_data=ACTION_EXPAND))
            buttons.append(InlineKeyboardButton("✍️ Перефразируй", callback_data=ACTION_REPHRASE))
    # Длинный ответ
    elif text_length >= config.POST_PROCESSING_LONG_THRESHOLD:
        buttons.append(InlineKeyboardButton("➡️⬅️ Сократи", callback_data=ACTION_SHORTEN))
        buttons.append(InlineKeyboardButton("✍️ Перефразируй", callback_data=ACTION_REPHRASE))
    
    if not buttons:
        return None
        
    return InlineKeyboardMarkup([buttons])


async def handle_post_processing_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """
    [Dev-Ассистент]: Обрабатывает нажатия на кнопки "Сократи", "Раскрой", "Перефразируй".
    """
    query = update.callback_query
    action = query.data

    # Проверяем, относится ли callback к нашим действиям
    if action not in ACTION_PROMPTS:
        return False # Это не наш callback, передаем управление дальше

    await query.answer()

    last_response = context.user_data.get(LAST_RESPONSE_KEY)
    if not last_response:
        await query.edit_message_reply_markup(None) # Убираем кнопки
        await query.message.reply_text("😔 Не удалось найти текст для обработки. Возможно, вы ждали слишком долго.")
        return True

    user_prompt = ACTION_PROMPTS[action]
    
    # [Dev-Ассистент]: Важно! Убираем кнопки со старого сообщения, чтобы избежать повторных нажатий.
    await query.edit_message_reply_markup(None)
    
    # [Dev-Ассистент]: Импортируем здесь, чтобы избежать циклических импортов.
    from main import process_ai_request

    # [Dev-Ассистент]: Мы не просто отправляем новый запрос, а "внедряемся" в основной поток.
    # [Dev-Ассистент]: Сначала добавляем последний ответ AI в историю как будто он там уже был.
    # [Dev-Ассистент]: А затем отправляем наш "скрытый" промпт ("Сократи" и т.д.).
    # [Dev-Ассистент]: Это обеспечивает полный контекст диалога!
    
    # Получаем user_data через декоратор не можем, поэтому собираем вручную
    from utils import inject_user_data
    
    # Оборачиваем простую лямбду, чтобы передать в декоратор
    async def wrapped_process(update, context, user_data):
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
        # Добавляем последний ответ модели в историю для контекста
        context.chat_data.setdefault('history', []).append({'role': 'model', 'parts': [last_response]})
        await process_ai_request(update, context, user_data, user_prompt)

    # Вызываем обернутую функцию
    await inject_user_data(wrapped_process)(update, context)

    return True