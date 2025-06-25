# database.py (Версия с aiosqlite)

import sqlite3 # Оставляем для первоначальной проверки и типа ошибки
import logging
import os
import aiosqlite # <<< ИЗМЕНЕНИЕ: Импортируем новую библиотеку
from typing import Any, Dict, List, Optional, Union
from datetime import datetime, timedelta, date

logger = logging.getLogger(__name__)
DB_FILE = os.path.join('data', 'gemini_bot.db')

# Функция _init_db остается без изменений, так как она вызывается один раз
# синхронно при старте и это нормально.
def _init_db():
    os.makedirs(os.path.dirname(DB_FILE), exist_ok=True)
    try:
        with sqlite3.connect(DB_FILE) as con:
            cur = con.cursor()
            cur.execute("PRAGMA foreign_keys = ON")
            # ... (весь остальной код создания таблиц не меняется) ...
            cur.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY,
                    telegram_id INTEGER UNIQUE NOT NULL,
                    full_name TEXT,
                    username TEXT,
                    current_character_name TEXT DEFAULT 'Помощник',
                    current_ai_provider TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    daily_requests_count INTEGER DEFAULT 0,
                    last_request_date TEXT,
                    subscription_tier TEXT DEFAULT 'free' NOT NULL,
                    is_verified BOOLEAN NOT NULL DEFAULT 0,
                    subscription_expiry_date DATETIME
                )
            """)
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
            logger.info("База данных успешно инициализирована (Архитектура: Подписки).")
    except sqlite3.Error as e:
        logger.error(f"Ошибка при инициализации базы данных SQLite: {e}", exc_info=True)
        raise

# <<< ИЗМЕНЕНИЕ: Полностью переписанная асинхронная функция db_request >>>
async def db_request(
    query: str, 
    params: tuple = (), 
    fetch_one: bool = False, 
    fetch_all: bool = False
) -> Any:
    """
    Выполняет асинхронный запрос к базе данных SQLite с использованием aiosqlite
    и возвращает результаты в виде стандартных словарей Python.
    """
    try:
        async with aiosqlite.connect(DB_FILE, timeout=10) as con:
            await con.execute("PRAGMA foreign_keys = ON")
            
            # Мы по-прежнему используем Row factory для удобства доступа по именам колонок.
            con.row_factory = aiosqlite.Row
            
            async with con.cursor() as cur:
                await cur.execute(query, params)

                if fetch_one:
                    row = await cur.fetchone()
                    # ===> ВОТ ИСПРАВЛЕНИЕ <===
                    # Если строка найдена, преобразуем ее в обычный dict перед возвратом.
                    return dict(row) if row else None
                
                if fetch_all:
                    rows = await cur.fetchall()
                    # ===> И ЗДЕСЬ ТОЖЕ <===
                    # Преобразуем каждую строку в списке в обычный dict.
                    return [dict(row) for row in rows]
                
                await con.commit()
                return cur.lastrowid

    except aiosqlite.Error as e:
        logger.error(f"Ошибка выполнения DB запроса: {query} с параметрами {params}. Ошибка: {e}", exc_info=True)
        return None

# --- ВАЖНО: Все остальные функции в файле (add_or_update_user, get_user_by_id и т.д.) ---
# --- остаются АБСОЛЮТНО БЕЗ ИЗМЕНЕНИЙ! Они уже используют db_request и будут ---
# --- автоматически работать с новой асинхронной версией. ---

# --- Пользователи ---
async def add_or_update_user(telegram_id: int, full_name: str, username: Optional[str]) -> Optional[int]:
    query = "INSERT INTO users (telegram_id, full_name, username) VALUES (?, ?, ?) ON CONFLICT(telegram_id) DO UPDATE SET full_name = excluded.full_name, username = excluded.username RETURNING id"
    result = await db_request(query, (telegram_id, full_name, username), fetch_one=True)
    return result['id'] if result else None

async def get_user_by_id(user_id: int) -> Optional[Dict]:
    return await db_request("SELECT * FROM users WHERE id = ?", (user_id,), fetch_one=True)

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
    query = "UPDATE users SET subscription_tier = ?, subscription_expiry_date = ?, daily_requests_count = 0, last_request_date = ? WHERE telegram_id = ?"
    await db_request(query, (tier, expiry_date, today_str, telegram_id))
    logger.info(f"Для пользователя telegram_id={telegram_id} установлен тариф '{tier}' до {expiry_date}")

async def set_user_tier_to_free(user_id: int):
    query = "UPDATE users SET subscription_tier = 'free', subscription_expiry_date = NULL WHERE id = ?"
    await db_request(query, (user_id,))
    logger.info(f"Подписка для user_id={user_id} сброшена до 'free'.")

# --- Персонажи и История (без изменений) ---
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

# Вызов _init_db() остается здесь
_init_db()