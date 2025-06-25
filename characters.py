import os
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Персонаж по умолчанию
DEFAULT_CHARACTER_NAME = "Базовый AI"

# --- НОВАЯ ЛОГИКА ЗАГРУЗКИ ПРОМПТОВ ---

def load_prompts_from_files() -> tuple[dict, dict]:
    """
    Сканирует директорию /prompts, загружает промпты из .txt файлов
    и возвращает два словаря: один со всеми промптами, другой с категориями.
    """
    all_prompts = {}
    character_categories = {}
    
    base_path = Path(__file__).parent / "prompts"
    
    if not base_path.exists():
        logger.error(f"Директория с промптами не найдена: {base_path}")
        return {}, {}
        
    for category_dir in base_path.iterdir():
        if category_dir.is_dir():
            category_name = category_dir.name
            character_categories[category_name] = []
            
            for prompt_file in category_dir.glob("*.txt"):
                character_name = prompt_file.stem  # Имя файла без расширения
                try:
                    with open(prompt_file, "r", encoding="utf-8") as f:
                        all_prompts[character_name] = f.read().strip()
                    character_categories[category_name].append(character_name)
                    logger.info(f"Загружен промпт для '{character_name}' из категории '{category_name}'")
                except Exception as e:
                    logger.error(f"Не удалось загрузить промпт из файла {prompt_file}: {e}")

    return all_prompts, character_categories

# Загружаем промпты один раз при запуске бота
ALL_PROMPTS, CHARACTER_CATEGORIES = load_prompts_from_files()