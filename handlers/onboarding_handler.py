# handlers/onboarding_handler.py (РЕФАКТОРИНГ НА HTML)

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.error import BadRequest

ONBOARDING_PAGES = [
    # [Dev-Ассистент]: Вся разметка заменена на HTML
    {
        "text": (
            "🤖 <b>Добро пожаловать в обучение от AGM!</b> \n\n"
            "Я проведу тебя по ключевым функциям бота, чтобы ты мог использовать его на 100%.\n\n"
            "Начнем с самого простого. Нажми 'Дальше', чтобы узнать о персонажах."
        ),
    },
    {
        "text": (
            "🎭 <b>Что такое 'Персонажи'?</b> \n\n"
            "Персонажи — это предустановленные роли для AI. Выбрав персонажа, ты задаешь "
            "модели определенный стиль общения и поведения. \n\n"
            "Например, можешь общаться с 'Маркетологом' для генерации идей или со 'Сценаристом' для помощи с сюжетом."
        ),
    },
    {
        "text": (
            "✍️ <b>Создание собственных персонажей</b>\n\n"
            "Самая мощная функция — ты можешь создавать своих персонажей! "
            "Для этого нужно задать 'промпт' — подробную инструкцию для AI, описывающую его роль, знания и манеру речи.\n\n"
            "Это позволяет создать узкоспециализированного помощника под любую твою задачу."
        ),
    },
    {
        "text": (
            "🧠 <b>Выбор AI модели</b>\n\n"
            "Бот поддерживает несколько разных AI моделей (например, Gemini, GPT). "
            "Каждая из них имеет свои сильные стороны. \n\n"
            "Ты можешь переключаться между ними в меню 'Выбор AI', чтобы найти лучшую модель для конкретной задачи."
        ),
    },
    {
        "text": (
            "🖼️ <b>Генерация изображений</b>\n\n"
            "Помимо текста, бот умеет создавать изображения с помощью нейросетей DALL-E 3 и YandexArt. "
            "Просто выбери соответствующий режим в меню 'Выбор AI' и отправь текстовое описание того, что хочешь нарисовать."
        ),
    },
    {
        "text": (
            "✅ <b>Обучение завершено!</b> \n\n"
            "Теперь ты знаешь об основных возможностях бота. Не бойся экспериментировать с промптами и моделями, "
            "чтобы достичь наилучших результатов. \n\n"
            "Удачи!"
        ),
    },
]

def _get_onboarding_keyboard(page_index: int) -> InlineKeyboardMarkup:
    buttons = []
    if page_index > 0:
        buttons.append(InlineKeyboardButton("⬅️ Назад", callback_data="onboarding_prev"))
    
    if page_index < len(ONBOARDING_PAGES) - 1:
        buttons.append(InlineKeyboardButton("➡️ Дальше", callback_data="onboarding_next"))

    if page_index == len(ONBOARDING_PAGES) - 1:
        buttons.append(InlineKeyboardButton("✅ Завершить", callback_data="onboarding_close"))
        
    return InlineKeyboardMarkup([buttons])

async def show_onboarding_page(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    page_index = context.user_data.get('onboarding_page_index', 0)
    
    page_content = ONBOARDING_PAGES[page_index]
    text = page_content["text"]
    reply_markup = _get_onboarding_keyboard(page_index)
    
    try:
        if query:
            # [Dev-Ассистент]: Меняем parse_mode
            await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='HTML')
        else:
            await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='HTML')
    except BadRequest as e:
        if "Message is not modified" in str(e):
            await query.answer()
        else:
            raise

async def handle_onboarding_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    query = update.callback_query
    if not query or not query.data.startswith("onboarding_"):
        return False
        
    await query.answer()
    
    if query.data == "onboarding_close":
        await query.edit_message_text("Отлично! Если захочешь перечитать, я всегда здесь. 👋")
        context.user_data.pop('onboarding_page_index', None)
        return True

    page_index = context.user_data.get('onboarding_page_index', 0)
    
    if query.data == "onboarding_next": page_index += 1
    elif query.data == "onboarding_prev": page_index -= 1
        
    context.user_data['onboarding_page_index'] = page_index
    
    await show_onboarding_page(update, context)
    
    return True

async def start_onboarding(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.setdefault('onboarding_page_index', 0)
    await show_onboarding_page(update, context)