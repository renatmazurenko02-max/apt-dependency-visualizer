"""Консольный запуск анализа графа зависимостей пакета."""

# argparse читает параметры запуска, sys нужен для ошибок и кода завершения.
import argparse
import sys
from pathlib import Path

from .config import ConfigError, load_config
from .graph import build_graph, format_graph
from .packages import RepositoryError, find_package
from .source import load_repository


SUCCESS = 0  # Терминал считает ноль признаком успешного завершения.
FAILURE = 1  # Ненулевой код сообщает об ошибке.
# Стандартный CSV ищем рядом с проектом независимо от папки запуска.
DEFAULT_CONFIG = Path(__file__).resolve().parent.parent / "config.csv"


def main(argv=None):
    """Прочитать настройки, построить граф и показать результат анализа."""
    # Путь к CSV можно передать при запуске; иначе берем config.csv проекта.
    parser = argparse.ArgumentParser(
        description="Вариант 13. Этап 3: рекурсивный обход зависимостей."
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
        # 4. Обходим зависимости с учетом глубины, фильтра и циклов.
        graph = build_graph(
            index, package, config.max_depth, config.filter_substring
        )
    except (ConfigError, RepositoryError, OSError, ValueError) as error:
        # Ошибку показываем пользователю и завершаемся с ненулевым кодом.
        print(f"Ошибка: {error}", file=sys.stderr)
        return FAILURE
    # 5. Передаем готовый граф выводу; позднее его получит визуализатор.
    print("\n".join(format_graph(graph)))
    return SUCCESS


if __name__ == "__main__":
    # При запуске модуля передаем терминалу код, возвращенный функцией main.
    raise SystemExit(main())
