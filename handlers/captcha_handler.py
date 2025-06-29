# handlers/captcha_handler.py (РЕФАКТОРИНГ НА HTML)

import random
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.error import BadRequest
import database as db
from utils import get_main_keyboard

async def send_captcha(update: Update, context: ContextTypes.DEFAULT_TYPE):
    num1 = random.randint(1, 10)
    num2 = random.randint(1, 10)
    correct_answer = num1 + num2
    
    context.user_data['captcha_answer'] = correct_answer
    
    answers = {correct_answer}
    while len(answers) < 4:
        wrong_answer = random.randint(2, 20)
        answers.add(wrong_answer)
        
    shuffled_answers = sorted(list(answers))
    
    keyboard = [InlineKeyboardButton(str(ans), callback_data=f"captcha_{ans}") for ans in shuffled_answers]
    reply_markup = InlineKeyboardMarkup([keyboard[i:i+2] for i in range(0, len(keyboard), 2)])
    
    # [Dev-Ассистент]: Меняем разметку на HTML
    text = (
        "🤖 <b>Добро пожаловать!</b>\n\n"
        "Чтобы защитить нашего бота от спама и обеспечить быструю работу для всех, "
        "пожалуйста, подтвердите, что вы не робот.\n\n"
        f"Сколько будет: <b>{num1} + {num2}</b>?"
    )
    
    message_to_use = update.message or update.callback_query.message
    
    try:
        if update.callback_query:
            await update.callback_query.edit_message_text(text, reply_markup=reply_markup, parse_mode='HTML')
        else:
            await message_to_use.reply_text(text, reply_markup=reply_markup, parse_mode='HTML')
    except BadRequest as e:
        if "Message is not modified" in str(e): await update.callback_query.answer()
        else: raise

async def handle_captcha_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    query = update.callback_query
    if not query or not query.data.startswith("captcha_"):
        return False

    user_answer = int(query.data.split('_')[1])
    correct_answer = context.user_data.get('captcha_answer')

    if user_answer == correct_answer:
        await query.answer("✅ Отлично! Проверка пройдена.", show_alert=True)
        user = update.effective_user
        await db.add_or_update_user(user.id, user.full_name, user.username)
        await db.verify_user(user.id)
        context.user_data.pop('captcha_answer', None)
        await query.delete_message()
        
        # [Dev-Ассистент]: Этот блок уже был на HTML, так что все хорошо.
        welcome_text = (
            f"Добро пожаловать, {user.mention_html()}!\n\n"
            "Я твой многофункциональный ассистент. "
            "Чтобы задать мне определенную роль или личность, воспользуйся меню <b>'Персонажи'</b>."
        )
        await context.bot.send_message(
            chat_id=update.effective_chat.id, text=welcome_text,
            reply_markup=get_main_keyboard(), parse_mode='HTML'
        )
    else:
        await query.answer("❌ Неверно, попробуйте еще раз.")
        await send_captcha(update, context)
        
    return True