import os
import logging
from pathlib import Path
import yaml
logger = logging.getLogger(__name__)
from constants import TIER_FREE

# Персонаж по умолчанию
DEFAULT_CHARACTER_NAME = "Базовый AI"

# --- НОВАЯ ЛОГИКА ЗАГРУЗКИ ПРОМПТОВ ---

def load_prompts_from_files() -> tuple[dict, dict]:
    """
    Сканирует директорию /prompts, загружает данные о персонажах из .yml файлов
    и возвращает два словаря: один со всеми данными персонажей, другой с категориями.
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
            
            # [Dev-Ассистент]: Ищем файлы с расширением .yml вместо .txt
            for prompt_file in category_dir.glob("*.yml"):
                character_name = prompt_file.stem
                try:
                    with open(prompt_file, "r", encoding="utf-8") as f:
                        # [Dev-Ассистент]: Используем yaml.safe_load для безопасного парсинга файла
                        data = yaml.safe_load(f)

                    # [Dev-Ассистент]: Проверяем, что файл не пустой и данные успешно загружены
                    if data:
                        # [Dev-Ассистент]: Сохраняем всего персонажа (описание и промпт) в виде словаря.
                        # [Dev-Ассистент]: Используем .get() для безопасности, чтобы код не упал, если
                        # [Dev-Ассистент]: в файле отсутствует description или prompt.
                        all_prompts[character_name] = {
                            'description': data.get('description', 'Описание для этого персонажа не задано.'),
                            'prompt': data.get('prompt', 'Системный промпт для этого персонажа не задан.'),
                            'required_tier': data.get('required_tier', TIER_FREE) # <<< [Dev-Ассистент]: НОВАЯ СТРОКА
                        }
                        character_categories[category_name].append(character_name)
                        logger.info(f"Загружен персонаж '{character_name}' из категории '{category_name}' (Тариф: {all_prompts[character_name]['required_tier']})") # [Dev-Ассистент]: Улучшенный лог
                    else:
                        logger.warning(f"Файл промпта {prompt_file} пуст или имеет неверный формат.")

                except yaml.YAMLError as e:
                    logger.error(f"Ошибка парсинга YAML в файле {prompt_file}: {e}")
                except Exception as e:
                    logger.error(f"Не удалось загрузить персонажа из файла {prompt_file}: {e}")

    return all_prompts, character_categories

# Загружаем промпты один раз при запуске бота
ALL_PROMPTS, CHARACTER_CATEGORIES = load_prompts_from_files()