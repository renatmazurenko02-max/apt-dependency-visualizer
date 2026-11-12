"""Консольный запуск анализа зависимостей пакета Ubuntu.

argparse разбирает команду, sys передает ошибки и код завершения.
SUCCESS=0 означает успех, FAILURE=1 означает ошибку.
По умолчанию CSV и папка generated расположены в корне проекта.
При запуске модуля SystemExit передает результат main терминалу.
"""

import argparse
import sys
from pathlib import Path

from .config import ConfigError, load_config
from .graph import build_graph, format_graph
from .packages import RepositoryError, find_package
from .reverse import build_reverse_graph
from .source import load_repository
from .tree import format_tree
from .visualize import export_graph, show_image


SUCCESS = 0
FAILURE = 1
DEFAULT_CONFIG = Path(__file__).resolve().parent.parent / "config.csv"
DEFAULT_OUTPUT = DEFAULT_CONFIG.parent / "generated"


def _analyze(index, package, config, reverse):
    """Выбрать направление анализа, сохранив одинаковые настройки обхода."""
    builder = build_reverse_graph if reverse else build_graph
    return builder(index, package, config.max_depth, config.filter_substring)


def _arguments(argv):
    """Разобрать путь к CSV и параметры запуска в объект args.

    Если путь не указан, использовать config.csv из корня проекта.
    Флаги выбирают направление, подробность вывода и создание PNG.
    """
    parser = argparse.ArgumentParser(
        description="Вариант 13. Визуализация зависимостей пакетов Ubuntu."
    )
    parser.add_argument(
        "config", nargs="?", default=DEFAULT_CONFIG, help="Путь к CSV-файлу"
    )
    parser.add_argument(
        "--reverse", action="store_true", help="Пакеты, которым нужен исходный"
    )
    parser.add_argument("--output", default=DEFAULT_OUTPUT, help="Папка файлов")
    parser.add_argument("--plantuml-jar", help="Путь к своему PlantUML JAR")
    parser.add_argument(
        "--no-image", action="store_true", help="Только текст, без Java и PNG"
    )
    parser.add_argument(
        "--no-open", action="store_true", help="Создать PNG без открытия окна"
    )
    parser.add_argument(
        "--details", action="store_true", help="Показать все узлы и связи"
    )
    return parser.parse_args(argv)


def _report(graph, config, artifacts, details):
    """Показать итог, необязательное дерево и пути к созданным файлам."""
    lines = format_graph(graph)
    if details:
        print("\n".join(lines))
    else:
        print(lines[0])
        if graph.reverse:
            print(lines[1])
        print(f"Узлов: {len(graph.nodes)}; связей: {len(graph.edges)}")
    if config.ascii_tree:
        print("ASCII-дерево:")
        print("\n".join(format_tree(graph, config.max_depth)))
    elif not graph.nodes:
        print("Исходный пакет исключен фильтром.")
    print("PlantUML: " + str(artifacts.source))
    if artifacts.image:
        print("PNG: " + str(artifacts.image))


def _execute(args):
    """Выполнить анализ и вернуть код успешного завершения.

    Прочитать настройки и каталог, найти точную версию пакета,
    построить граф и передать готовые связи визуализатору.
    Затем вывести отчет и открыть PNG, если это разрешено флагами.
    """
    config = load_config(args.config)
    index = load_repository(config, args.config)
    package = find_package(index, config.package_name, config.package_version)
    graph = _analyze(index, package, config, args.reverse)
    if not args.no_image:
        print("Создание изображения PlantUML...")
    artifacts = export_graph(
        graph, config, args.output, not args.no_image, args.plantuml_jar
    )
    _report(graph, config, artifacts, args.details)
    if artifacts.image and not args.no_open:
        show_image(artifacts.image)
    return SUCCESS


def main(argv=None):
    """Разобрать команду, запустить анализ и вернуть код завершения.

    Ожидаемые ошибки вывести в stderr и вернуть FAILURE.
    При успешном выполнении вернуть код из _execute.
    """
    args = _arguments(argv)
    try:
        return _execute(args)
    except (ConfigError, RepositoryError, OSError, ValueError) as error:
        print(f"Ошибка: {error}", file=sys.stderr)
        return FAILURE


if __name__ == "__main__":
    raise SystemExit(main())
