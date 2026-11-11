"""Консольный запуск получения прямых зависимостей пакета."""

import argparse
import sys
from pathlib import Path

from .config import ConfigError, load_config
from .packages import RepositoryError, find_package, format_dependency
from .source import load_repository


SUCCESS = 0
FAILURE = 1
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
        config = load_config(args.config)
        index = load_repository(config, args.config)
        package = find_package(
            index, config.package_name, config.package_version
        )
    except (ConfigError, RepositoryError, OSError, ValueError) as error:
        # Ошибку показываем пользователю и завершаемся с ненулевым кодом.
        print(f"Ошибка: {error}", file=sys.stderr)
        return FAILURE
    print(f"Прямые зависимости {package.name} (версия {package.version}):")
    if not package.dependencies:
        print("Нет прямых зависимостей.")
    for group in package.dependencies:
        print("  " + format_dependency(group))
    return SUCCESS


if __name__ == "__main__":
    raise SystemExit(main())
