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
        with sqlite3.connect(DB_FILE) as con:
            cur = con.cursor()
            cur.execute("PRAGMA foreign_keys = ON")
            
            cur.execute("""
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
            # [Dev-Ассистент]: Добавляем индекс для быстрого поиска рефералов
            cur.execute("CREATE INDEX IF NOT EXISTS idx_users_referred_by ON users (referred_by_user_id);")

            cur.execute("""
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
            cur.execute("CREATE INDEX IF NOT EXISTS idx_transactions_user_id ON transactions (user_id);")

            cur.execute("""
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

            cur.execute("""
                CREATE TABLE IF NOT EXISTS chat_history (
                    id INTEGER PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    character_name TEXT NOT NULL,
                    role TEXT NOT NULL CHECK(role IN ('user', 'model')),
                    content TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
                )
            """)
            cur.execute("CREATE INDEX IF NOT EXISTS idx_chat_history_user_char ON chat_history (user_id, character_name);")

            con.commit()
            logger.info("База данных успешно инициализирована (Архитектура: Подписки, Кошелек, Рефералы).")
    except sqlite3.Error as e:
        logger.error(f"Ошибка при инициализации базы данных SQLite: {e}", exc_info=True)
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
        if 'con' in locals() and con.is_connected():
            await con.rollback()
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

# --- Персонажи и История (остались без изменений) ---
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
async def add_message_to_history(user_id: int, character_name: str, role: str, content: str) -> None:
    query = "INSERT INTO chat_history (user_id, character_name, role, content) VALUES (?, ?, ?, ?)"
    await db_request(query, (user_id, character_name, role, content))
async def get_chat_history(user_id: int, character_name: str, limit: int = 30) -> List[Dict]:
    query = "SELECT role, content FROM chat_history WHERE user_id = ? AND character_name = ? ORDER BY id DESC LIMIT ?"
    rows = await db_request(query, (user_id, character_name, limit), fetch_all=True)
    if not rows: return []
    return [{"role": row['role'], "parts": [row['content']]} for row in reversed(rows)]
async def clear_chat_history(user_id: int, character_name: str) -> None:
    query = "DELETE FROM chat_history WHERE user_id = ? AND character_name = ?"
    await db_request(query, (user_id, character_name))
async def get_history_length(user_id: int, character_name: str) -> int:
    query = "SELECT COUNT(id) FROM chat_history WHERE user_id = ? AND character_name = ?"
    result = await db_request(query, (user_id, character_name), fetch_one=True)
    return result['COUNT(id)'] if result else 0
async def trim_chat_history(user_id: int, character_name: str, keep_last_n: int) -> None:
    query = "DELETE FROM chat_history WHERE user_id = ? AND character_name = ? AND id NOT IN (SELECT id FROM chat_history WHERE user_id = ? AND character_name = ? ORDER BY id DESC LIMIT ?)"
    await db_request(query, (user_id, character_name, user_id, character_name, keep_last_n))

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