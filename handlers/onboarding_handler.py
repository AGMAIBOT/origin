# handlers/onboarding_handler.py
# [Dev-Ассистент]: НОВЫЙ ФАЙЛ ДЛЯ ИНТЕРАКТИВНОГО ОБУЧЕНИЯ

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.error import BadRequest

# --- "КНИГА": Хранилище страниц нашего обучения ---
# [Dev-Ассистент]: Денис, тебе нужно будет только поменять тексты здесь.
# [Dev-Ассистент]: Все остальное будет работать автоматически.

ONBOARDING_PAGES = [
    # Страница 0
    {
        "text": (
            "🤖 *Добро пожаловать в обучение от AGM!* \n\n"
            "Я проведу тебя по ключевым функциям бота, чтобы ты мог использовать его на 100%.\n\n"
            "Начнем с самого простого. Нажми 'Дальше', чтобы узнать о персонажах."
        ),
    },
    # Страница 1
    {
        "text": (
            "🎭 *Что такое 'Персонажи'?* \n\n"
            "Персонажи — это предустановленные роли для AI. Выбрав персонажа, ты задаешь "
            "модели определенный стиль общения и поведения. \n\n"
            "Например, можешь общаться с 'Маркетологом' для генерации идей или со 'Сценаристом' для помощи с сюжетом."
        ),
    },
    # Страница 2
    {
        "text": (
            "✍️ *Создание собственных персонажей*\n\n"
            "Самая мощная функция — ты можешь создавать своих персонажей! "
            "Для этого нужно задать 'промпт' — подробную инструкцию для AI, описывающую его роль, знания и манеру речи.\n\n"
            "Это позволяет создать узкоспециализированного помощника под любую твою задачу."
        ),
    },
    # Страница 3
    {
        "text": (
            "🧠 *Выбор AI модели*\n\n"
            "Бот поддерживает несколько разных AI моделей (например, Gemini, GPT). "
            "Каждая из них имеет свои сильные стороны. \n\n"
            "Ты можешь переключаться между ними в меню 'Выбор AI', чтобы найти лучшую модель для конкретной задачи."
        ),
    },
    # Страница 4
    {
        "text": (
            "🖼️ *Генерация изображений*\n\n"
            "Помимо текста, бот умеет создавать изображения с помощью нейросетей DALL-E 3 и YandexArt. "
            "Просто выбери соответствующий режим в меню 'Выбор AI' и отправь текстовое описание того, что хочешь нарисовать."
        ),
    },
    # Страница 5
    {
        "text": (
            "✅ *Обучение завершено!* \n\n"
            "Теперь ты знаешь об основных возможностях бота. Не бойся экспериментировать с промптами и моделями, "
            "чтобы достичь наилучших результатов. \n\n"
            "Удачи!"
        ),
    },
    # Страница 6
    {
        "text": (
            " *РЕЗЕРВ!* \n\n"
            "Теперь ты знаешь об основных возможностях бота. Не бойся экспериментировать с промптами и моделями, "
            "чтобы достичь наилучших результатов. \n\n"
            "Удачи!"
        ),
    }
]

# --- ЛОГИКА: Функции для "перелистывания" страниц ---

def _get_onboarding_keyboard(page_index: int) -> InlineKeyboardMarkup:
    """Собирает клавиатуру в зависимости от номера текущей страницы."""
    buttons = []
    # Кнопка "Назад" появляется на всех страницах, кроме первой (индекс 0)
    if page_index > 0:
        buttons.append(InlineKeyboardButton("⬅️ Назад", callback_data="onboarding_prev"))
    
    # Кнопка "Дальше" появляется на всех страницах, кроме последней
    if page_index < len(ONBOARDING_PAGES) - 1:
        buttons.append(InlineKeyboardButton("➡️ Дальше", callback_data="onboarding_next"))

    # Если мы на последней странице, добавим кнопку "Завершить"
    if page_index == len(ONBOARDING_PAGES) - 1:
        buttons.append(InlineKeyboardButton("✅ Завершить", callback_data="onboarding_close"))
        
    return InlineKeyboardMarkup([buttons])

async def show_onboarding_page(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Главная функция, которая показывает или обновляет страницу обучения.
    """
    query = update.callback_query
    # Получаем "закладку" - номер текущей страницы из user_data.
    # Если ее нет, начинаем с 0.
    page_index = context.user_data.get('onboarding_page_index', 0)
    
    # Получаем текст и клавиатуру для текущей страницы
    page_content = ONBOARDING_PAGES[page_index]
    text = page_content["text"]
    reply_markup = _get_onboarding_keyboard(page_index)
    
    try:
        # Если функция вызвана через нажатие на кнопку (query существует),
        # то мы редактируем существующее сообщение.
        if query:
            await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
        # Если это первый запуск (из главного меню), то отправляем новое сообщение.
        else:
            await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')
    except BadRequest as e:
        # Игнорируем ошибку "сообщение не изменилось", если пользователь тыкает на одну и ту же кнопку
        if "Message is not modified" in str(e):
            await query.answer() # Отвечаем на callback, чтобы убрать часики на кнопке
        else:
            raise

async def handle_onboarding_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """
    Обрабатывает нажатия на кнопки "Дальше", "Назад" и "Завершить".
    Возвращает True, если callback был обработан, иначе False.
    """
    query = update.callback_query
    if not query or not query.data.startswith("onboarding_"):
        return False
        
    await query.answer()
    
    # Закрываем окно обучения
    if query.data == "onboarding_close":
        await query.edit_message_text("Отлично! Если захочешь перечитать, я всегда здесь. 👋")
        context.user_data.pop('onboarding_page_index', None) # Удаляем "закладку"
        return True

    # Получаем текущую страницу
    page_index = context.user_data.get('onboarding_page_index', 0)
    
    # "Перелистываем" страницу
    if query.data == "onboarding_next":
        page_index += 1
    elif query.data == "onboarding_prev":
        page_index -= 1
        
    # Сохраняем новую "закладку"
    context.user_data['onboarding_page_index'] = page_index
    
    # Показываем новую страницу
    await show_onboarding_page(update, context)
    
    return True

async def start_onboarding(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    [Dev-Ассистент]: УМНАЯ ВЕРСИЯ.
    Запускает процесс обучения или продолжает с того места, где пользователь остановился.
    """
    # [Dev-Ассистент]: ИСПОЛЬЗУЕМ setdefault.
    # [Dev-Ассистент]: Это элегантный способ сказать: "посмотри в user_data, есть ли ключ 'onboarding_page_index'.
    # [Dev-Ассистент]: Если он есть - ничего не делай. Если его нет - создай его со значением 0".
    context.user_data.setdefault('onboarding_page_index', 0)
    
    # [Dev-Ассистент]: Теперь эта функция всегда будет показывать правильную страницу:
    # [Dev-Ассистент]: либо 0 для нового пользователя, либо сохраненную для вернувшегося.
    await show_onboarding_page(update, context)