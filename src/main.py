"""Консольная точка входа первого этапа."""

import argparse
import sys
from dataclasses import asdict
from pathlib import Path

from .config import ConfigError, load_config


SUCCESS = 0
FAILURE = 1
DEFAULT_CONFIG = Path(__file__).resolve().parent.parent / "config.csv"


def main(argv=None):
    """Прочитать конфигурацию и вывести параметры или понятную ошибку."""
    # Путь к CSV можно передать при запуске; иначе берем config.csv проекта.
    parser = argparse.ArgumentParser(
        description="Вариант 13. Этап 1: чтение настроек из CSV."
    )
    parser.add_argument(
        "config", nargs="?", default=DEFAULT_CONFIG, help="Путь к CSV-файлу"
    )
    args = parser.parse_args(argv)
    try:
        config = load_config(args.config)
    except (ConfigError, OSError, ValueError) as error:
        # Ошибку показываем пользователю и завершаемся с ненулевым кодом.
        print(f"Ошибка: {error}", file=sys.stderr)
        return FAILURE
    for key, value in asdict(config).items():
        # Переключатели печатаем так же, как они записаны в CSV.
        if isinstance(value, bool):
            value = str(value).lower()
        print(f"{key}={value}")
    return SUCCESS


if __name__ == "__main__":
    raise SystemExit(main())
