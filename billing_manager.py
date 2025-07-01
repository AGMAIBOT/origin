# billing_manager.py

import logging
import html
from typing import Dict, Any

from telegram import Update
from telegram.ext import ContextTypes

import database as db
import config
from constants import TRANSACTION_TYPE_IMAGE_GEN_COST, TRANSACTION_TYPE_TOPUP # Импортируем нужные типы транзакций

logger = logging.getLogger(__name__)

async def get_item_cost(item_type: str, item_identifier: str) -> int:
    """
    Централизованная функция для получения стоимости услуги в AGMcoin.
    
    :param item_type: Тип услуги (например, 'dalle3_image_gen').
    :param item_identifier: Идентификатор конкретной услуги (например, '1024x1024' для DALL-E 3).
    :return: Стоимость услуги в AGMcoin.
    :raises ValueError: Если тип услуги или идентификатор не найден.
    """
    cost_usd = 0

    if item_type == 'dalle3_image_gen':
        if item_identifier not in config.DALL_E_3_PRICING:
            logger.error(f"Неизвестный идентификатор разрешения DALL-E 3: {item_identifier}")
            raise ValueError(f"Неизвестный идентификатор разрешения DALL-E 3: {item_identifier}")
        cost_usd = config.DALL_E_3_PRICING[item_identifier]['cost_usd']
    # [Dev-Ассистент]: Сюда можно будет добавлять другие типы платных услуг в будущем
    # elif item_type == 'some_other_paid_service':
    #     # Логика определения стоимости для другой услуги
    #     pass
    else:
        logger.error(f"Неизвестный тип платной услуги: {item_type}")
        raise ValueError(f"Неизвестный тип платной услуги: {item_type}")

    return int(cost_usd * config.USD_TO_AGM_RATE)

async def perform_deduction(
    user_id: int, 
    item_type: str, # Например, 'dalle3_image_gen'
    item_identifier: str, # Например, '1024x1024'
    update: Update, 
    context: ContextTypes.DEFAULT_TYPE
) -> bool:
    """
    Выполняет попытку списания средств за услугу.
    Отправляет пользователю уведомление, если средств недостаточно.
    
    :param user_id: ID пользователя в БД.
    :param item_type: Тип услуги (например, 'dalle3_image_gen').
    :param item_identifier: Идентификатор конкретной услуги (например, '1024x1024').
    :param update: Объект Update из Telegram.
    :param context: Объект ContextTypes.DEFAULT_TYPE из Telegram.
    :return: True, если списание успешно (или средств достаточно), False в противном случае.
    """
    try:
        cost_agm = await get_item_cost(item_type, item_identifier)
    except ValueError as e:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=f"Ошибка в определении стоимости услуги: {e}"
        )
        return False

    user_account_data = await db.get_user_by_id(user_id)
    if not user_account_data:
        logger.error(f"Пользователь с ID {user_id} не найден при попытке списания.")
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="Произошла ошибка при получении данных вашего профиля."
        )
        return False
        
    user_balance = user_account_data.get('balance', 0)

    if user_balance < cost_agm:
        # [Dev-Ассистент]: Улучшенный текст сообщения с HTML форматированием
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=(
                f"😔 <b>Недостаточно AGMcoin для выполнения операции.</b>\n\n"
                f"Ваш баланс: <code>{user_balance}</code> AGMcoin.\n"
                f"Требуется: <code>{cost_agm}</code> AGMcoin.\n\n"
                f"Пополните баланс в разделе ⚙️ Профиль -> 👛 Кошелек."
            ),
            parse_mode='HTML'
        )
        return False

    # [Dev-Ассистент]: Описание транзакции будет более детальным
    description = f"Оплата {item_type.replace('_', ' ')}: {item_identifier} ({cost_agm} AGMcoin)"
    
    # Вызываем универсальную функцию обновления баланса из database.py
    success = await db.update_user_balance(
        user_id, 
        -cost_agm, # Списываем средства
        TRANSACTION_TYPE_IMAGE_GEN_COST, # Используем специфичный тип транзакции
        description=description
    )
    
    if not success:
        logger.error(f"Не удалось списать {cost_agm} AGMcoin с user_id={user_id} за {item_type}:{item_identifier}")
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="Произошла ошибка при списании средств. Пожалуйста, попробуйте позже."
        )
        return False
        
    return True