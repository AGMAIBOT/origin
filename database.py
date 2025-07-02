# database.py (ОБНОВЛЕННАЯ ВЕРСИЯ - ДОБАВЛЕН referred_by_user_id)

import sqlite3
import logging
import os
import aiosqlite
from typing import Any, Dict, List, Optional, Union
from datetime import datetime, timedelta, date

logger = logging.getLogger(__name__)
DB_FILE = os.path.join('data', 'gemini_bot.db')

import config
import constants

def _init_db():
    os.makedirs(os.path.dirname(DB_FILE), exist_ok=True)
    try:
        async def init_db_async(): # [Dev-Ассистент]: Временная асинхронная обертка для aiosqlite
            async with aiosqlite.connect(DB_FILE) as con:
                await con.execute("PRAGMA foreign_keys = ON")
                
                # [Dev-Ассистент]: Обновляем схему chat_history
                await con.execute("""
                    CREATE TABLE IF NOT EXISTS users (
                        id INTEGER PRIMARY KEY,
                        telegram_id INTEGER UNIQUE NOT NULL,
                        full_name TEXT,
                        username TEXT,
                        current_character_name TEXT DEFAULT 'Базовый AI',
                        current_ai_provider TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        daily_requests_count INTEGER DEFAULT 0,
                        last_request_date TEXT,
                        subscription_tier TEXT DEFAULT 'free' NOT NULL,
                        is_verified BOOLEAN NOT NULL DEFAULT 0,
                        subscription_expiry_date DATETIME,
                        output_format TEXT DEFAULT 'text' NOT NULL,
                        balance INTEGER DEFAULT 0 NOT NULL,
                        referred_by_user_id INTEGER DEFAULT NULL,
                        default_dalle3_resolution TEXT DEFAULT NULL,
                        default_yandexart_resolution TEXT DEFAULT NULL,        
                        FOREIGN KEY (referred_by_user_id) REFERENCES users (id) ON DELETE SET NULL -- <<< [Dev-Ассистент]: СВЯЗЬ
                    )
                """)
                await con.execute("CREATE INDEX IF NOT EXISTS idx_users_referred_by ON users (referred_by_user_id);")
                # [Dev-Ассистент]: Добавляем индекс для быстрого поиска рефералов
                await con.execute("CREATE INDEX IF NOT EXISTS idx_users_referred_by ON users (referred_by_user_id);")

                await con.execute("""
                    CREATE TABLE IF NOT EXISTS transactions (
                        id INTEGER PRIMARY KEY,
                        user_id INTEGER NOT NULL,
                        amount INTEGER NOT NULL,
                        type TEXT NOT NULL,
                        description TEXT,
                        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        external_id TEXT,
                        balance_before INTEGER,
                        balance_after INTEGER,
                        FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
                    )
                """)

                await con.execute("CREATE INDEX IF NOT EXISTS idx_transactions_user_id ON transactions (user_id);")

                await con.execute("""
                    CREATE TABLE IF NOT EXISTS characters (
                        id INTEGER PRIMARY KEY,
                        user_id INTEGER NOT NULL,
                        name TEXT NOT NULL,
                        prompt TEXT NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE,
                        UNIQUE (user_id, name)
                    )
                """)

                # [Dev-Ассистент]: Модифицированная таблица chat_history
                await con.execute("""
                    CREATE TABLE IF NOT EXISTS chat_history (
                        id INTEGER PRIMARY KEY,
                        user_id INTEGER NOT NULL,
                        character_name TEXT NOT NULL,
                        role TEXT NOT NULL CHECK(role IN ('user', 'model')),
                        content TEXT NOT NULL,
                        token_count INTEGER NOT NULL DEFAULT 0, -- [Dev-Ассистент]: НОВЫЙ СТОЛБЕЦ
                        is_summary BOOLEAN NOT NULL DEFAULT 0,  -- [Dev-Ассистент]: НОВЫЙ СТОЛБЕЦ
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
                    )
                """)
                await con.execute("CREATE INDEX IF NOT EXISTS idx_chat_history_user_char ON chat_history (user_id, character_name);")
                # [Dev-Ассистент]: Добавляем индекс для is_summary, чтобы ускорить поиск резюме
                await con.execute("CREATE INDEX IF NOT EXISTS idx_chat_history_is_summary ON chat_history (user_id, character_name, is_summary);")

                await con.execute("CREATE INDEX IF NOT EXISTS idx_chat_history_user_char ON chat_history (user_id, character_name);")
                # [Dev-Ассистент]: Добавляем индекс для is_summary, чтобы ускорить поиск резюме
                await con.execute("CREATE INDEX IF NOT EXISTS idx_chat_history_is_summary ON chat_history (user_id, character_name, is_summary);")

                await con.commit()
                logger.info("База данных успешно инициализирована (Архитектура: Подписки, Кошелек, Рефералы, Динамический Контекст).")             
        # Запускаем асинхронную функцию из синхронного контекста (для инициализации)
        # Это хак, т.к. _init_db вызывается в синхронном окружении.
        # В рабочем коде (например, в main.py) db_request всегда будет вызываться асинхронно.
        import asyncio
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        loop.run_until_complete(init_db_async())

    except sqlite3.Error as e:
        logger.error(f"Ошибка при инициализации базы данных SQLite: {e}", exc_info=True)
        raise
    except Exception as e: # [Dev-Ассистент]: Общая ошибка на случай проблем с asyncio
        logger.error(f"Непредвиденная ошибка при инициализации базы данных: {e}", exc_info=True)
        raise

async def db_request(
    query: str, 
    params: tuple = (), 
    fetch_one: bool = False, 
    fetch_all: bool = False
) -> any:
    """
    Выполняет асинхронный запрос к базе данных SQLite с использованием aiosqlite
    и ГАРАНТИРОВАННО СОХРАНЯЕТ ИЗМЕНЕНИЯ перед возвратом результата.
    """
    try:
        async with aiosqlite.connect(DB_FILE, timeout=10) as con:
            await con.execute("PRAGMA foreign_keys = ON")
            
            con.row_factory = aiosqlite.Row
            
            async with con.cursor() as cur:
                await cur.execute(query, params)

                result = None
                if fetch_one:
                    row = await cur.fetchone()
                    result = dict(row) if row else None
                elif fetch_all:
                    rows = await cur.fetchall()
                    result = [dict(row) for row in rows]
                else:
                    result = cur.lastrowid
                
                await con.commit()
                
                return result

    except aiosqlite.Error as e:
        logger.error(f"Ошибка выполнения DB запроса: {query} с параметрами {params}. Ошибка: {e}", exc_info=True)
        # [Dev-Ассистент]: Rollback не нужен, т.к. aiosqlite.connect() как контекстный менеджер
        # [Dev-Ассистент]: откатит изменения при исключении автоматически.
        return None

def _get_default_ai_provider_for_tier(tier_name: str) -> str:
    """Возвращает AI-провайдера по умолчанию для указанного тарифного плана."""
    tier_config = config.SUBSCRIPTION_TIERS.get(tier_name, config.SUBSCRIPTION_TIERS[constants.TIER_FREE])
    return tier_config.get('ai_provider', constants.GPT_1)

# --- Пользователи ---
# [Dev-Ассистент]: Обновили add_or_update_user, чтобы он принимал referer_id
async def add_or_update_user(telegram_id: int, full_name: str, username: Optional[str], referer_id: Optional[int] = None) -> Optional[int]:
    existing_user = await db_request("SELECT id, subscription_tier, current_ai_provider, referred_by_user_id FROM users WHERE telegram_id = ?", (telegram_id,), fetch_one=True)
    
    if existing_user:
        # [Dev-Ассистент]: Если пользователь существует, обновляем его имя и юзернейм.
        # [Dev-Ассистент]: И если referer_id передан и в БД его еще нет, записываем.
        update_params = [full_name, username, telegram_id]
        update_query = "UPDATE users SET full_name = ?, username = ?"
        
        if referer_id is not None and existing_user.get('referred_by_user_id') is None:
            update_query += ", referred_by_user_id = ?"
            update_params.insert(0, referer_id) # Добавляем referer_id в начало, чтобы он соответствовал ?
            # Переставляем telegram_id в конец
            update_params = update_params[1:] + [update_params[0]] 
            logger.info(f"Обновлен пользователь telegram_id={telegram_id}: добавлен реферер user_id={referer_id}.")

        update_query += " WHERE telegram_id = ? RETURNING id"
        result = await db_request(update_query, tuple(update_params), fetch_one=True)
        return result['id'] if result else None
    else:
        # [Dev-Ассистент]: Если пользователь новый, создаем его с реферером (если есть)
        default_tier = constants.TIER_FREE
        default_ai_provider = _get_default_ai_provider_for_tier(default_tier)
        
        query = "INSERT INTO users (telegram_id, full_name, username, subscription_tier, current_ai_provider, balance, referred_by_user_id) VALUES (?, ?, ?, ?, ?, ?, ?) RETURNING id"
        result = await db_request(query, (telegram_id, full_name, username, default_tier, default_ai_provider, 0, referer_id), fetch_one=True)
        logger.info(f"Создан новый пользователь telegram_id={telegram_id} с тарифом '{default_tier}', AI '{default_ai_provider}', баланс: 0, реферер: {referer_id or 'None'}.")
        return result['id'] if result else None


async def get_user_by_id(user_id: int) -> Optional[Dict]:
    return await db_request("SELECT * FROM users WHERE id = ?", (user_id,), fetch_one=True)

# [Dev-Ассистент]: НОВАЯ ВСПОМОГАТЕЛЬНАЯ ФУНКЦИЯ: получить реферера пользователя
async def get_referrer_for_user(user_id: int) -> Optional[Dict]:
    """Возвращает данные реферера для указанного пользователя."""
    query = "SELECT U2.* FROM users AS U1 JOIN users AS U2 ON U1.referred_by_user_id = U2.id WHERE U1.id = ?"
    return await db_request(query, (user_id,), fetch_one=True)

async def get_and_update_user_usage(user_id: int, daily_limit: int) -> Dict:
    today_str = date.today().isoformat()
    user_usage = await db_request("SELECT daily_requests_count, last_request_date FROM users WHERE id = ?", (user_id,), fetch_one=True)
    if not user_usage:
        return {"can_request": False, "requests_left": 0, "limit": daily_limit}
    last_request_date_str = user_usage.get('last_request_date')
    current_count = user_usage.get('daily_requests_count', 0)
    if last_request_date_str != today_str:
        await db_request("UPDATE users SET daily_requests_count = 1, last_request_date = ? WHERE id = ?", (today_str, user_id))
        return {"can_request": True, "requests_left": daily_limit - 1, "limit": daily_limit}
    if current_count >= daily_limit:
        return {"can_request": False, "requests_left": 0, "limit": daily_limit}
    await db_request("UPDATE users SET daily_requests_count = daily_requests_count + 1 WHERE id = ?", (user_id,))
    return {"can_request": True, "requests_left": daily_limit - (current_count + 1), "limit": daily_limit}

async def set_user_subscription(telegram_id: int, tier: str, duration_days: int) -> None:
    expiry_date = None
    if tier != 'free':
        expiry_date = datetime.now() + timedelta(days=duration_days)
    today_str = date.today().isoformat()
    
    new_default_ai_provider = _get_default_ai_provider_for_tier(tier)
    
    query = "UPDATE users SET subscription_tier = ?, subscription_expiry_date = ?, daily_requests_count = 0, last_request_date = ?, current_ai_provider = ? WHERE telegram_id = ?"
    await db_request(query, (tier, expiry_date, today_str, new_default_ai_provider, telegram_id))
    logger.info(f"Для пользователя telegram_id={telegram_id} установлен тариф '{tier}' до {expiry_date}, AI по умолчанию: '{new_default_ai_provider}'")

async def set_user_tier_to_free(user_id: int):
    default_free_ai_provider = _get_default_ai_provider_for_tier(constants.TIER_FREE)
    query = "UPDATE users SET subscription_tier = 'free', subscription_expiry_date = NULL, current_ai_provider = ? WHERE id = ?"
    await db_request(query, (default_free_ai_provider, user_id,))
    logger.info(f"Подписка для user_id={user_id} сброшена до 'free'. AI установлен на '{default_free_ai_provider}'.")

async def add_transaction(
    user_id: int, 
    amount: int, 
    transaction_type: str, 
    description: Optional[str] = None, 
    external_id: Optional[str] = None,
    balance_before: Optional[int] = None,
    balance_after: Optional[int] = None
) -> Optional[int]:
    """
    Добавляет запись о финансовой транзакции в базу данных.
    :param user_id: ID пользователя.
    :param amount: Изменение баланса (может быть отрицательным для списаний).
    :param transaction_type: Тип транзакции (topup, request_cost, referral_bonus, purchase, referral_commission).
    :param description: Описание.
    :param external_id: Внешний ID (например, ID платежа).
    :param balance_before: Баланс пользователя до транзакции (для аудита).
    :param balance_after: Баланс пользователя после транзакции (для аудита).
    :return: ID новой транзакции или None.
    """
    query = """
        INSERT INTO transactions (user_id, amount, type, description, external_id, balance_before, balance_after)
        VALUES (?, ?, ?, ?, ?, ?, ?) RETURNING id
    """
    result = await db_request(
        query, 
        (user_id, amount, transaction_type, description, external_id, balance_before, balance_after), 
        fetch_one=True
    )
    return result['id'] if result else None

# [Dev-Ассистент]: НОВАЯ ФУНКЦИЯ: Обновление баланса пользователя (с записью транзакции и реферальным бонусом)
async def update_user_balance(
    user_id: int, 
    amount_change: int, 
    transaction_type: str, 
    description: Optional[str] = None, 
    external_id: Optional[str] = None
) -> bool:
    """
    Изменяет баланс пользователя и записывает транзакцию.
    Если transaction_type - 'topup', проверяет наличие реферера и начисляет ему процент.
    :param user_id: ID пользователя.
    :param amount_change: Сумма изменения баланса (положительная для пополнения, отрицательная для списания).
    :param transaction_type: Тип транзакции.
    :param description: Описание.
    :param external_id: Внешний ID (для платежных систем).
    :return: True, если обновление успешно, False в противном случае.
    """
    user = await get_user_by_id(user_id)
    if not user:
        logger.error(f"Пользователь с ID {user_id} не найден для обновления баланса.")
        return False

    old_balance = user.get('balance', 0)
    new_balance = old_balance + amount_change

    # Обновляем баланс в таблице users
    update_query = "UPDATE users SET balance = ? WHERE id = ?"
    await db_request(update_query, (new_balance, user_id))

    # Добавляем запись о транзакции
    await add_transaction(
        user_id, 
        amount_change, 
        transaction_type, 
        description, 
        external_id,
        old_balance,
        new_balance
    )
    logger.info(f"Баланс user_id={user_id} изменен на {amount_change}. Новый баланс: {new_balance}.")

    # [Dev-Ассистент]: ЛОГИКА РЕФЕРАЛЬНОГО ПРОЦЕНТА
    if transaction_type == constants.TRANSACTION_TYPE_TOPUP and amount_change > 0:
        referrer = await get_referrer_for_user(user_id)
        if referrer:
            referrer_user_id = referrer['id']
            commission_amount = int(amount_change * config.REFERRAL_PERCENTAGE / 100) # Процент от пополнения
            if commission_amount > 0:
                logger.info(f"Начисление реферальной комиссии: {commission_amount} AGMcoin рефереру {referrer_user_id} от пополнения {user_id}.")
                # Начисляем комиссию рефереру
                await update_user_balance(
                    referrer_user_id, 
                    commission_amount, 
                    constants.TRANSACTION_TYPE_REFERRAL_COMMISSION,
                    f"Реферальная комиссия от пополнения пользователя {user.get('username', user.get('telegram_id'))} ({amount_change} AGMcoin)"
                )

    return True

# [Dev-Ассистент]: НОВАЯ ФУНКЦИЯ: Получить рефералов пользователя
async def get_user_referrals(user_id: int) -> List[Dict]:
    """Возвращает список пользователей, приглашенных данным реферером."""
    query = "SELECT id, telegram_id, username, full_name, created_at FROM users WHERE referred_by_user_id = ?"
    return await db_request(query, (user_id,), fetch_all=True)

# [Dev-Ассистент]: НОВАЯ ФУНКЦИЯ: Получить суммарный реферальный доход пользователя
async def get_user_referral_earnings(user_id: int) -> int:
    """Возвращает общую сумму AGMcoin, заработанную по реферальной программе."""
    query = "SELECT SUM(amount) FROM transactions WHERE user_id = ? AND type = ?"
    result = await db_request(query, (user_id, constants.TRANSACTION_TYPE_REFERRAL_COMMISSION), fetch_one=True)
    return result['SUM(amount)'] if result and result['SUM(amount)'] is not None else 0

# --- Персонажи и История ---
# [Dev-Ассистент]: Модифицированная функция: теперь принимает token_count и is_summary
async def add_message_to_history(user_id: int, character_name: str, role: str, content: str, token_count: int, is_summary: bool = False) -> None:
    """
    Добавляет сообщение в историю чата с подсчитанным количеством токенов.
    :param user_id: ID пользователя.
    :param character_name: Имя персонажа.
    :param role: Роль ('user' или 'model').
    :param content: Текст сообщения.
    :param token_count: Количество токенов в сообщении.
    :param is_summary: Флаг, указывающий, является ли сообщение резюме.
    """
    query = "INSERT INTO chat_history (user_id, character_name, role, content, token_count, is_summary) VALUES (?, ?, ?, ?, ?, ?)"
    await db_request(query, (user_id, character_name, role, content, token_count, is_summary))

# [Dev-Ассистент]: НОВАЯ ФУНКЦИЯ: Получает историю для формирования контекста LLM (резюме + активный буфер)
async def get_history_for_context(user_id: int, character_name: str, active_buffer_count: int) -> List[Dict]:
    """
    Извлекает историю чата для формирования контекста LLM:
    - Последнее глобальное резюме (если есть)
    - Последние N оригинальных сообщений (активный буфер)
    
    :param user_id: ID пользователя.
    :param character_name: Имя персонажа.
    :param active_buffer_count: Количество сообщений в активном буфере.
    :return: Список сообщений в формате для LLM (роль, контент).
    """
    messages = []

    # 1. Получаем последнее глобальное резюме
    summary_query = """
        SELECT role, content FROM chat_history
        WHERE user_id = ? AND character_name = ? AND is_summary = 1
        ORDER BY id DESC LIMIT 1
    """
    latest_summary = await db_request(summary_query, (user_id, character_name), fetch_one=True)
    if latest_summary:
        messages.append({"role": latest_summary['role'], "parts": [latest_summary['content']]})
        logger.debug(f"Получено последнее резюме для user_id={user_id}, char='{character_name}'.")

    # 2. Получаем сообщения для активного буфера
    # Здесь мы выбираем active_buffer_count *последних* сообщений, которые НЕ ЯВЛЯЮТСЯ резюме
    active_buffer_query = """
        SELECT role, content FROM chat_history
        WHERE user_id = ? AND character_name = ? AND is_summary = 0
        ORDER BY id DESC LIMIT ?
    """
    active_buffer_messages = await db_request(active_buffer_query, (user_id, character_name, active_buffer_count), fetch_all=True)
    
    # Сообщения из активного буфера должны быть в хронологическом порядке (старые первыми)
    if active_buffer_messages:
        # [Dev-Ассистент]: Преобразуем формат, так как AI клиенты ожидают список словарей с 'parts'
        messages.extend([{"role": msg['role'], "parts": [msg['content']]} for msg in reversed(active_buffer_messages)])
        logger.debug(f"Получен активный буфер ({len(active_buffer_messages)} сообщений) для user_id={user_id}, char='{character_name}'.")

    return messages

# [Dev-Ассистент]: НОВАЯ ФУНКЦИЯ: Получает сообщения для суммаризации
async def get_messages_for_summarization(user_id: int, character_name: str, active_buffer_count: int) -> List[Dict]:
    """
    Извлекает все оригинальные сообщения, которые находятся ЗА пределами активного буфера,
    и которые еще не были суммированы (т.е. не являются is_summary=1).
    Возвращает сообщения и их ID для последующего удаления.
    
    :param user_id: ID пользователя.
    :param character_name: Имя персонажа.
    :param active_buffer_count: Количество сообщений в активном буфере.
    :return: Список словарей с ключами 'id', 'role', 'content' для суммаризации.
    """
    # Определяем ID N последних несжатых сообщений (активный буфер)
    latest_non_summary_ids_query = """
        SELECT id FROM chat_history
        WHERE user_id = ? AND character_name = ? AND is_summary = 0
        ORDER BY id DESC LIMIT ?
    """
    latest_non_summary_ids_rows = await db_request(latest_non_summary_ids_query, (user_id, character_name, active_buffer_count), fetch_all=True)
    latest_non_summary_ids = [row['id'] for row in latest_non_summary_ids_rows]

    # Извлекаем все остальные несжатые сообщения (те, что нужно суммировать)
    summarizable_messages_query = f"""
        SELECT id, role, content FROM chat_history
        WHERE user_id = ? AND character_name = ? AND is_summary = 0
        {'AND id NOT IN ({})'.format(','.join(map(str, latest_non_summary_ids))) if latest_non_summary_ids else ''}
        ORDER BY id ASC
    """
    # [Dev-Ассистент]: Важно: если нет ID для исключения, не добавлять подзапрос с IN ()
    params = (user_id, character_name)
    
    messages_to_summarize = await db_request(summarizable_messages_query, params, fetch_all=True)
    
    if messages_to_summarize:
        logger.debug(f"Получено {len(messages_to_summarize)} сообщений для суммаризации для user_id={user_id}, char='{character_name}'.")
    else:
        logger.debug(f"Нет сообщений для суммаризации для user_id={user_id}, char='{character_name}'.")

    return messages_to_summarize

# [Dev-Ассистент]: НОВАЯ ФУНКЦИЯ: Получает сумму токенов в сообщениях, которые нужно суммировать
async def get_total_tokens_in_summarizable_history(user_id: int, character_name: str, active_buffer_count: int) -> int:
    """
    Возвращает суммарное количество токенов всех оригинальных сообщений,
    которые находятся ЗА пределами активного буфера и подлежат суммаризации.
    
    :param user_id: ID пользователя.
    :param character_name: Имя персонажа.
    :param active_buffer_count: Количество сообщений в активном буфере.
    :return: Общее количество токенов.
    """
    # Определяем ID N последних несжатых сообщений (активный буфер)
    latest_non_summary_ids_query = """
        SELECT id FROM chat_history
        WHERE user_id = ? AND character_name = ? AND is_summary = 0
        ORDER BY id DESC LIMIT ?
    """
    latest_non_summary_ids_rows = await db_request(latest_non_summary_ids_query, (user_id, character_name, active_buffer_count), fetch_all=True)
    latest_non_summary_ids = [row['id'] for row in latest_non_summary_ids_rows]

    # Суммируем токены всех остальных несжатых сообщений
    total_tokens_query = f"""
        SELECT SUM(token_count) AS total_tokens FROM chat_history
        WHERE user_id = ? AND character_name = ? AND is_summary = 0
        {'AND id NOT IN ({})'.format(','.join(map(str, latest_non_summary_ids))) if latest_non_summary_ids else ''}
    """
    params = (user_id, character_name)

    result = await db_request(total_tokens_query, params, fetch_one=True)
    total_tokens = result['total_tokens'] if result and result['total_tokens'] is not None else 0
    
    logger.debug(f"Сумма токенов для суммаризации для user_id={user_id}, char='{character_name}': {total_tokens}.")
    return total_tokens

# [Dev-Ассистент]: НОВАЯ ФУНКЦИЯ: Сохраняет новое резюме и удаляет старые сообщения
async def save_summary_and_clean_old_messages(
    user_id: int, 
    character_name: str, 
    summary_text: str, 
    summary_token_count: int, 
    old_messages_to_delete_ids: List[int]
) -> None:
    """
    Выполняет атомарную транзакцию:
    1. Удаляет все сообщения с указанными ID.
    2. Удаляет предыдущее глобальное резюме для данного диалога.
    3. Вставляет новое сообщение-резюме.
    
    :param user_id: ID пользователя.
    :param character_name: Имя персонажа.
    :param summary_text: Текст нового резюме.
    :param summary_token_count: Количество токенов нового резюме.
    :param old_messages_to_delete_ids: Список ID оригинальных сообщений, которые нужно удалить.
    """
    try:
        async with aiosqlite.connect(DB_FILE, timeout=10) as con:
            await con.execute("PRAGMA foreign_keys = ON")
            
            # 1. Удаляем сообщения, которые только что были суммированы
            if old_messages_to_delete_ids:
                placeholders = ','.join('?' * len(old_messages_to_delete_ids))
                delete_old_query = f"""
                    DELETE FROM chat_history WHERE user_id = ? AND character_name = ? AND id IN ({placeholders})
                """
                await con.execute(delete_old_query, (user_id, character_name, *old_messages_to_delete_ids))
                logger.debug(f"Удалено {len(old_messages_to_delete_ids)} старых сообщений для user_id={user_id}, char='{character_name}'.")

            # 2. Удаляем предыдущее глобальное резюме (если оно было)
            delete_prev_summary_query = """
                DELETE FROM chat_history
                WHERE user_id = ? AND character_name = ? AND is_summary = 1
            """
            await con.execute(delete_prev_summary_query, (user_id, character_name))
            logger.debug(f"Удалено предыдущее резюме для user_id={user_id}, char='{character_name}'.")

            # 3. Вставляем новое резюме
            insert_summary_query = """
                INSERT INTO chat_history (user_id, character_name, role, content, token_count, is_summary)
                VALUES (?, ?, ?, ?, ?, ?)
            """
            await con.execute(insert_summary_query, (user_id, character_name, 'model', summary_text, summary_token_count, True))
            logger.info(f"Сохранено новое резюме ({summary_token_count} токенов) для user_id={user_id}, char='{character_name}'.")

            await con.commit()
            logger.info(f"Атомарная операция суммаризации для user_id={user_id}, char='{character_name}' успешно завершена.")

    except aiosqlite.Error as e:
        logger.error(f"Ошибка при атомарной операции сохранения резюме и очистки: {e}", exc_info=True)
        # Rollback будет выполнен автоматически aiosqlite.connect как контекстным менеджером

# [Dev-Ассистент]: get_chat_history, trim_chat_history, get_history_length, set_current_character
# [Dev-Ассистент]: Эти функции больше не нужны для формирования контекста LLM, но остаются для других целей.
# [Dev-Ассистент]: get_chat_history теперь не используется для LLM-контекста, его функционал заменяет get_history_for_context.
# [Dev-Ассистент]: trim_chat_history больше не нужна, её логика заменяется суммаризацией и удалением.
# [Dev-Ассистент]: get_history_length также теряет актуальность для управления контекстом.

async def add_character(user_id: int, name: str, prompt: str) -> Optional[int]:
    return await db_request("INSERT INTO characters (user_id, name, prompt) VALUES (?, ?, ?)", (user_id, name, prompt))
async def get_user_characters(user_id: int) -> List[Dict]:
    return await db_request("SELECT id, name, prompt FROM characters WHERE user_id = ? ORDER BY name", (user_id,), fetch_all=True)
async def get_custom_character_by_name(user_id: int, name: str) -> Optional[Dict]:
    return await db_request("SELECT id, name, prompt FROM characters WHERE user_id = ? AND name = ?", (user_id, name), fetch_one=True)
async def update_character(character_id: int, new_name: str, new_prompt: str) -> None:
    await db_request("UPDATE characters SET name = ?, prompt = ? WHERE id = ?", (new_name, new_prompt, character_id))
async def delete_character(character_id: int) -> None:
    await db_request("DELETE FROM characters WHERE id = ?", (character_id,))
async def set_current_character(user_id: int, character_name: str) -> None:
    await db_request("UPDATE users SET current_character_name = ? WHERE id = ?", (character_name, user_id))
async def get_character_by_id(character_id: int) -> Optional[Dict]:
    return await db_request("SELECT id, name, prompt FROM characters WHERE id = ?", (character_id,), fetch_one=True)
# [Dev-Ассистент]: Эта функция теперь используется для отображения истории в интерфейсе, а не для LLM-контекста.
async def get_chat_history(user_id: int, character_name: str, limit: int = 30) -> List[Dict]:
    query = "SELECT role, content FROM chat_history WHERE user_id = ? AND character_name = ? ORDER BY id DESC LIMIT ?"
    rows = await db_request(query, (user_id, character_name, limit), fetch_all=True)
    if not rows: return []
    # [Dev-Ассистент]: Возвращаем в универсальном формате, который ожидает LLM-клиент
    return [{"role": row['role'], "parts": [row['content']]} for row in reversed(rows)]
async def clear_chat_history(user_id: int, character_name: str) -> None:
    # [Dev-Ассистент]: Эта функция теперь будет удалять все записи (и обычные, и резюме)
    query = "DELETE FROM chat_history WHERE user_id = ? AND character_name = ?"
    await db_request(query, (user_id, character_name))
# [Dev-Ассистент]: Эта функция теперь для общих целей, не для контекста LLM.
async def get_history_length(user_id: int, character_name: str) -> int:
    query = "SELECT COUNT(id) FROM chat_history WHERE user_id = ? AND character_name = ?"
    result = await db_request(query, (user_id, character_name), fetch_one=True)
    return result['COUNT(id)'] if result else 0
# [Dev-Ассистент]: trim_chat_history больше не актуальна в контексте новой логики суммаризации
# async def trim_chat_history(user_id: int, character_name: str, keep_last_n: int) -> None:
#     query = "DELETE FROM chat_history WHERE user_id = ? AND character_name = ? AND id NOT IN (SELECT id FROM chat_history WHERE user_id = ? AND character_name = ? ORDER BY id DESC LIMIT ?)"
#     await db_request(query, (user_id, character_name, user_id, character_name, keep_last_n))

async def get_user_by_telegram_id(telegram_id: int) -> Optional[Dict]:
    return await db_request("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,), fetch_one=True)

async def verify_user(telegram_id: int) -> None:
    await db_request("UPDATE users SET is_verified = 1 WHERE telegram_id = ?", (telegram_id,))

async def set_user_output_format(user_id: int, output_format: str) -> None:
    """Устанавливает предпочтительный формат вывода для пользователя."""
    query = "UPDATE users SET output_format = ? WHERE id = ?"
    await db_request(query, (output_format, user_id))
    logger.info(f"Для пользователя user_id={user_id} установлен формат вывода '{output_format}'.")

async def set_user_default_image_resolution(user_id: int, provider_type: str, resolution: str) -> None:
    """
    Устанавливает разрешение по умолчанию для выбранного AI-художника для данного пользователя.
    :param user_id: ID пользователя в БД.
    :param provider_type: Тип провайдера ('dalle3' или 'yandexart').
    :param resolution: Строковое представление разрешения (например, '1024x1024').
    """
    column_name = None
    if provider_type == constants.IMAGE_GEN_DALL_E_3: # Используем константу для безопасности
        column_name = "default_dalle3_resolution"
    elif provider_type == constants.IMAGE_GEN_YANDEXART: # Используем константу для безопасности
        column_name = "default_yandexart_resolution"
    else:
        logger.error(f"Попытка установить дефолтное разрешение для неизвестного типа провайдера: {provider_type}")
        return

    query = f"UPDATE users SET {column_name} = ? WHERE id = ?"
    await db_request(query, (resolution, user_id))
    logger.info(f"Для user_id={user_id} установлено дефолтное разрешение {resolution} для {provider_type}.")

# Вызов _init_db() остается здесь
_init_db()