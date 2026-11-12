"""Последовательно показать работу всех этапов одной командой.

FORWARD_CASES и REVERSE_CASES задают учебные примеры. Для них
вызывается тот же код анализа, что и при обычном запуске проекта.
"""

import argparse
import csv
import os
import re
import subprocess
import sys
import tempfile
from contextlib import redirect_stdout
from dataclasses import asdict
from pathlib import Path

from src.config import ConfigError, load_config
from src.graph import build_graph, format_graph
from src.packages import find_package, format_dependency
from src.reverse import build_reverse_graph
from src.source import _decode, _download, load_repository
from src.tree import format_tree
from src.visualize import export_graph, plantuml_source, show_image

from .demo import CONFIGS, INDEX_NAME, ROOT, WORK, catalog


FORWARD_CASES = (
    ("Обычный DFS и косвенные зависимости", "config.csv"),
    ("Ограничение глубины: один переход", "config-depth.csv"),
    ("Исключение пакета B и его ветки", "config-filter.csv"),
    ("Цикл с сохранением замыкающей связи", "config-cycle.csv"),
    ("Общая зависимость и более короткий путь", "config-shared.csv"),
)
REVERSE_CASES = (
    ("Прямые и косвенные потребители B", "config-reverse.csv"),
    ("Обратный поиск с глубиной 1", "config-reverse-depth.csv"),
    ("Обратный поиск с фильтром A", "config-reverse-filter.csv"),
    ("Обратный поиск в цикле", "config-cycle.csv"),
    ("Пакет без потребителей", "config-reverse-empty.csv"),
)
INVALID_VALUES = (
    ("package_name", "invalid name"), ("repository", "missing.json"),
    ("test_mode", "yes"), ("package_version", "abc"),
    ("ascii_tree", "yes"), ("max_depth", "-1"),
    ("filter_substring", "li\nb"),
)
DEMONSTRATION_ERRORS = (
    OSError, ValueError, RuntimeError, subprocess.SubprocessError,
)


class Stopped(Exception):
    """Пользователь завершил показ на одной из пауз."""


class Tee:
    """Одновременно записывать вывод в терминал и текстовый протокол."""

    def __init__(self, terminal, logfile):
        """Сохранить оба назначения без изменения обычного вывода программы."""
        self.terminal = terminal
        self.logfile = logfile

    def write(self, text):
        """Показать фрагмент и сохранить его в протоколе."""
        self.terminal.write(text)
        self.logfile.write(text)
        return len(text)

    def flush(self):
        """Сразу показать сообщения, в том числе перед ожиданием Enter."""
        self.terminal.flush()
        self.logfile.flush()


def setting_text(value):
    """Печатать переключатели как true/false, сохраняя регистр имен и путей."""
    return str(value).lower() if isinstance(value, bool) else str(value)


def invalid_examples(config, directory=None):
    """Выдать ошибки семи настроек на временных копиях CSV.

    Рабочий CSV сохранить неизменным. Путь к JSON сделать абсолютным,
    поскольку временный файл находится в другой папке.
    """
    values = {key: setting_text(value) for key, value in asdict(config).items()}
    values["repository"] = str(ROOT / "examples/repository.json")
    with tempfile.TemporaryDirectory(
        dir=directory, prefix="config-check-"
    ) as tmp:
        filename = Path(tmp) / "invalid.csv"
        for key, value in INVALID_VALUES:
            changed = dict(values, **{key: value})
            with filename.open("w", encoding="utf-8", newline="") as stream:
                writer = csv.writer(stream)
                writer.writerow(["parameter", "value"])
                writer.writerows(changed.items())
            try:
                load_config(filename)
            except ConfigError as error:
                yield key, value, str(error)
            else:
                raise RuntimeError("Не обнаружена ожидаемая ошибка: " + key)


class Presentation:
    """Управлять порядком показа, используя готовые функции проекта."""

    def __init__(self, args):
        """Настроить паузы, папку вывода и начальное состояние показа.

        index и checksum заполняются после свежей загрузки второго этапа.
        """
        self.args = args
        self.output = Path(args.output).resolve()
        self.index = None
        self.checksum = None

    def pause(self):
        """Дать время объяснить результат; q позволяет закончить показ."""
        if not self.args.no_pause:
            answer = input("\nEnter: продолжить; q: закончить показ. ")
            print()
            if answer.strip().lower() == "q":
                raise Stopped()

    def stage1(self):
        """Показать чтение CSV и реальные ошибки каждого параметра."""
        print("\nЭТАП 1. Чтение и проверка конфигурации CSV")
        config = load_config(ROOT / "config.csv")
        for key, value in asdict(config).items():
            print(f"{key}={setting_text(value)}")
        print("\nОшибочные значения: ошибки ниже ожидаемы и обрабатываются.")
        for key, value, error in invalid_examples(config, self.output):
            print(f"\n{key}={value!r}")
            print("Ошибка: " + error)
        print("\nРабочие CSV не изменены: проверялись временные файлы.")
        self.pause()

    def stage2(self):
        """Заново скачать каталог и показать прямые зависимости пакета.

        Свежая загрузка обязательна даже при наличии локальной копии.
        Сохранить индекс и SHA-256 для следующих этапов и сверки отчета.
        """
        print("\nЭТАП 2. Свежая загрузка из репозитория Ubuntu")
        config = load_config(ROOT / CONFIGS[0])
        print("URL: " + config.repository, flush=True)
        text = _decode(_download(config.repository))
        filename = WORK / "lists" / INDEX_NAME
        filename.parent.mkdir(parents=True, exist_ok=True)
        filename.write_text(text, encoding="utf-8")
        self.index, self.checksum = catalog(WORK)
        print(f"Загрузка завершена: {len(self.index)} записей.")
        print("SHA-256: " + self.checksum)
        package = find_package(
            self.index, config.package_name, config.package_version
        )
        print(f"Прямые зависимости {package.name} ({package.version}):")
        for group in package.dependencies:
            print("  " + format_dependency(group))
        self.pause()

    def example(self, title, filename, reverse=False):
        """Обработать учебный CSV в выбранном направлении и показать граф."""
        print("\nПример: " + title)
        print("Настройки: " + filename)
        path = ROOT / filename
        config = load_config(path)
        index = load_repository(config, path)
        root = find_package(index, config.package_name, config.package_version)
        builder = build_reverse_graph if reverse else build_graph
        graph = builder(index, root, config.max_depth, config.filter_substring)
        print("\n".join(format_graph(graph)))
        self.pause()

    def stage3(self):
        """Показать все основные случаи прямого рекурсивного DFS."""
        print("\nЭТАП 3. Рекурсивный обход, глубина, фильтр и циклы")
        for title, filename in FORWARD_CASES:
            self.example(title, filename)

    def stage4(self):
        """Показать потребителей выбранного пакета и ограничения поиска."""
        print("\nЭТАП 4. Обратные зависимости")
        for title, filename in REVERSE_CASES:
            self.example(title, filename, reverse=True)

    def visual_example(self, filename):
        """Построить реальный граф из нового каталога и открыть его рисунок."""
        config = load_config(ROOT / filename)
        package = find_package(
            self.index, config.package_name, config.package_version
        )
        graph = build_graph(self.index, package, config.max_depth)
        print(f"\nПакет {package.name}, версия {package.version}")
        print(f"Узлов: {len(graph.nodes)}; связей: {len(graph.edges)}")
        if config.ascii_tree:
            print("ASCII-дерево:")
            print("\n".join(format_tree(graph, config.max_depth)))
        files = export_graph(
            graph, config, self.output / "stage5", not self.args.no_image
        )
        print("PlantUML: " + str(files.source))
        if files.image:
            print("PNG: " + str(files.image))
            if not self.args.no_open:
                show_image(files.image)
        self.pause()

    def stage5(self):
        """Показать язык PlantUML и три изображения настоящих пакетов."""
        print("\nЭТАП 5. PlantUML, изображения и ASCII-дерево")
        path = ROOT / "config.csv"
        config = load_config(path)
        index = load_repository(config, path)
        root = find_package(index, config.package_name, config.package_version)
        graph = build_graph(index, root, config.max_depth)
        print("\nТекст PlantUML на небольшом учебном графе:")
        print(plantuml_source(graph))
        self.pause()
        for filename in CONFIGS:
            self.visual_example(filename)
        self.comparison()

    def comparison(self):
        """Явно различать сохраненный отчет и новый запуск штатного apt."""
        if self.args.compare:
            from .compare_apt import native, report
            from .demo import prepare
            print("\nНовое сравнение во временном Ubuntu, нужен Docker.")
            work = prepare()
            native(work)
            report(work)
        filename = ROOT / "docs/comparison.md"
        text = filename.read_text(encoding="utf-8")
        heading = (
            "Сравнение с apt, выполненное в этом показе:"
            if self.args.compare else "Сохраненный отчет сравнения с apt:"
        )
        print("\n" + heading)
        for line in text.splitlines():
            if line.startswith(("Среда:", "|")):
                print(line)
        expected = re.search(r"SHA-256 каталога: `([0-9a-f]+)`", text)
        if expected and expected.group(1) == self.checksum:
            print("Свежий каталог совпадает с каталогом сохраненного отчета.")
        else:
            print("Каталог отличается: для нового сравнения нужен --compare.")
        print("Полный отчет: " + str(filename))
        self.pause()

    def tests(self):
        """Запустить настоящие автотесты, а не печатать заранее заданное OK."""
        if self.args.no_tests:
            return
        print("\nПроверка проекта: запуск всех автотестов", flush=True)
        result = subprocess.run(
            [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-q"],
            cwd=ROOT, capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=120, check=False,
            env=dict(os.environ, PYTHONIOENCODING="utf-8"),
        )
        print(result.stdout + result.stderr)
        if result.returncode:
            raise RuntimeError("Автотесты завершились с ошибкой.")

    def run(self):
        """Последовательно вызвать все части демонстрации."""
        print("Показ пяти этапов конфигурационного управления. Вариант 13.")
        print("В этапе 2 требуется интернет: каталог скачивается заново.")
        for stage in (self.stage1, self.stage2, self.stage3,
                      self.stage4, self.stage5, self.tests):
            stage()
        print("\nПоказ всех пяти этапов завершен.")


def arguments(argv):
    """Настроить обычный показ или автоматическую проверку без окон."""
    parser = argparse.ArgumentParser(
        description="Показ всех этапов одной командой"
    )
    parser.add_argument("--output", default=ROOT / "generated/defense")
    parser.add_argument("--no-pause", action="store_true", help="Без пауз")
    parser.add_argument(
        "--no-open", action="store_true", help="Не открывать PNG"
    )
    parser.add_argument("--no-image", action="store_true", help="Без PNG")
    parser.add_argument("--no-tests", action="store_true", help="Без тестов")
    parser.add_argument(
        "--compare", action="store_true", help="Заново сравнить с apt в Docker"
    )
    return parser.parse_args(argv)


def record_error(filename, error):
    """Вывести ошибку в stderr и добавить ее в протокол при возможности.

    Если запись протокола недоступна, сохранить исходное сообщение
    в терминале и не заменять его дополнительной ошибкой записи.
    """
    message = "Ошибка демонстрации: " + str(error)
    print(message, file=sys.stderr)
    try:
        with filename.open("a", encoding="utf-8") as stream:
            stream.write(message + "\n")
    except OSError:
        pass


def main(argv=None):
    """Вести текстовый протокол и завершаться с понятным статусом."""
    args = arguments(argv)
    output = Path(args.output).resolve()
    filename = output / "transcript.txt"
    try:
        output.mkdir(parents=True, exist_ok=True)
        with filename.open("w", encoding="utf-8") as stream:
            with redirect_stdout(Tee(sys.stdout, stream)):
                try:
                    Presentation(args).run()
                except Stopped:
                    print("\nПоказ остановлен пользователем.")
    except DEMONSTRATION_ERRORS as error:
        record_error(filename, error)
        return 1
    except EOFError:
        print("Нет ввода для паузы. Используйте --no-pause.", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nПоказ прерван.")
        return 130
    print("Протокол: " + str(filename))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
