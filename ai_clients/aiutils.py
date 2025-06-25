from typing import List, Dict

def prepare_openai_history(
    system_instruction_content: str, 
    chat_history: List[Dict], 
    user_prompt: str
) -> List[Dict]:
    """
    Готовит полную историю чата для OpenAI-совместимых API.
    
    - Устанавливает системную инструкцию.
    - Конвертирует историю из формата Gemini ('model' -> 'assistant').
    - Добавляет текущий запрос пользователя.
    
    :param system_instruction_content: Текст системного промпта.
    :param chat_history: История сообщений в "универсальном" формате.
    :param user_prompt: Новый запрос от пользователя.
    :return: Список сообщений, готовый для отправки в API.
    """
    
    # Системная инструкция всегда идет первой
    messages = [{"role": "system", "content": system_instruction_content}]

    # Конвертируем основную историю
    for msg in chat_history:
        # Пропускаем возможные "пустые" или поврежденные сообщения
        if not (msg.get("parts") and msg["parts"][0]):
            continue

        # <<< DEV-АССИСТЕНТ: Ключевое преобразование роли >>>
        role = "assistant" if msg["role"] == "model" else msg["role"]
        
        messages.append({"role": role, "content": msg["parts"][0]})
    
    # В конце добавляем текущий запрос пользователя
    messages.append({"role": "user", "content": user_prompt})
    
    return messages