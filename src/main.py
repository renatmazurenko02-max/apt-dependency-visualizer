"""Консольный запуск анализа графа зависимостей пакета."""

# argparse читает параметры запуска, sys нужен для ошибок и кода завершения.
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


SUCCESS = 0  # Терминал считает ноль признаком успешного завершения.
FAILURE = 1  # Ненулевой код сообщает об ошибке.
# Стандартный CSV ищем рядом с проектом независимо от папки запуска.
DEFAULT_CONFIG = Path(__file__).resolve().parent.parent / "config.csv"
DEFAULT_OUTPUT = DEFAULT_CONFIG.parent / "generated"


def _analyze(index, package, config, reverse):
    """Выбрать направление анализа, сохранив одинаковые настройки обхода."""
    builder = build_reverse_graph if reverse else build_graph
    return builder(index, package, config.max_depth, config.filter_substring)


def _arguments(argv):
    """Прочитать путь к CSV и выбрать режим вывода результата."""
    # Путь к CSV можно передать при запуске; иначе берем config.csv проекта.
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
    """Соединить настройки, получение данных, DFS и визуализацию."""
    # 1. Получаем проверенные настройки и каталог пакетов.
    config = load_config(args.config)
    index = load_repository(config, args.config)
    # 2. Выбираем точную версию корневого пакета.
    package = find_package(index, config.package_name, config.package_version)
    # 3. Строим граф в выбранном направлении.
    graph = _analyze(index, package, config, args.reverse)
    # 4. Передаем готовый результат визуализатору, не вычисляя связи заново.
    if not args.no_image:
        print("Создание изображения PlantUML...")
    artifacts = export_graph(
        graph, config, args.output, not args.no_image, args.plantuml_jar
    )
    _report(graph, config, artifacts, args.details)
    # Пользовательский запуск открывает рисунок стандартной программой.
    if artifacts.image and not args.no_open:
        show_image(artifacts.image)
    return SUCCESS


def main(argv=None):
    """Запустить работу и превратить ожидаемые ошибки в понятное сообщение."""
    args = _arguments(argv)
    try:
        return _execute(args)
    except (ConfigError, RepositoryError, OSError, ValueError) as error:
        # Ошибку показываем пользователю и завершаемся с ненулевым кодом.
        print(f"Ошибка: {error}", file=sys.stderr)
        return FAILURE


if __name__ == "__main__":
    # При запуске модуля передаем терминалу код, возвращенный функцией main.
    raise SystemExit(main())
