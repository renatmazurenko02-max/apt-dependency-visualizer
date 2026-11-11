"""Консольный запуск получения прямых зависимостей пакета."""

# argparse читает параметры запуска, sys нужен для ошибок и кода завершения.
import argparse
import sys
from pathlib import Path

from .config import ConfigError, load_config
from .packages import RepositoryError, find_package, format_dependency
from .source import load_repository


SUCCESS = 0  # Терминал считает ноль признаком успешного завершения.
FAILURE = 1  # Ненулевой код сообщает об ошибке.
# Стандартный CSV ищем рядом с проектом независимо от папки запуска.
DEFAULT_CONFIG = Path(__file__).resolve().parent.parent / "config.csv"


def main(argv=None):
    """Прочитать настройки, получить пакет и показать прямые зависимости."""
    # Путь к CSV можно передать при запуске; иначе берем config.csv проекта.
    parser = argparse.ArgumentParser(
        description="Вариант 13. Этап 2: прямые зависимости пакета Ubuntu."
    )
    parser.add_argument(
        "config", nargs="?", default=DEFAULT_CONFIG, help="Путь к CSV-файлу"
    )
    args = parser.parse_args(argv)
    try:
        # 1. Читаем CSV и получаем проверенные настройки.
        config = load_config(args.config)
        # 2. Получаем индекс пакетов из интернета или учебного JSON.
        index = load_repository(config, args.config)
        # 3. Выбираем пакет с точным совпадением имени и версии.
        package = find_package(
            index, config.package_name, config.package_version
        )
    except (ConfigError, RepositoryError, OSError, ValueError) as error:
        # Ошибку показываем пользователю и завершаемся с ненулевым кодом.
        print(f"Ошибка: {error}", file=sys.stderr)
        return FAILURE
    # 4. Показываем только прямые зависимости найденной версии пакета.
    print(f"Прямые зависимости {package.name} (версия {package.version}):")
    if not package.dependencies:
        print("Нет прямых зависимостей.")
    # Одна строка соответствует одной группе; внутри могут быть альтернативы.
    for group in package.dependencies:
        print("  " + format_dependency(group))
    return SUCCESS


if __name__ == "__main__":
    # При запуске модуля передаем терминалу код, возвращенный функцией main.
    raise SystemExit(main())
