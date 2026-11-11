"""Чтение CSV-конфигурации и проверка пользовательских параметров."""

# Стандартные инструменты для CSV, шаблонов текста и путей к файлам.
import csv
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit


# Все настройки обязательны, даже если значение фильтра пустое.
FIELDS = (
    "package_name",
    "repository",
    "test_mode",
    "package_version",
    "ascii_tree",
    "max_depth",
    "filter_substring",
)
HEADER = ["parameter", "value"]  # Ожидаемые названия столбцов CSV.
COLUMN_COUNT = len(HEADER)  # В каждой строке нужны название и значение.
MIN_DEPTH = 0  # Нулевая глубина оставляет только исходный пакет.
# Разные шаблоны позволяют отличать учебные имена от имен Ubuntu.
PACKAGE_PATTERN = r"[a-z0-9][a-z0-9+.-]+"
TEST_PACKAGE_PATTERN = r"[A-Z]+"
VERSION_PATTERN = r"(?:[0-9]+:)?[0-9][A-Za-z0-9.+:~\-]*"


class ConfigError(ValueError):
    """Ошибка структуры CSV или значения параметра."""


@dataclass(frozen=True)
class Config:
    """Проверенные настройки; глубина ноль означает только корневой пакет."""

    # frozen=True защищает проверенные настройки от случайного изменения.
    package_name: str  # Какой пакет исследуем.
    repository: str  # Откуда получаем сведения: URL или учебный файл.
    test_mode: bool  # Используем ли учебный файл вместо сервера Ubuntu.
    package_version: str  # Какая именно версия исходного пакета нужна.
    ascii_tree: bool  # Нужно ли текстовое дерево на этапе визуализации.
    max_depth: int  # Насколько далеко разрешен будущий обход графа.
    filter_substring: str  # Какие имена исключать при будущем обходе.


def _read_rows(path):
    """Прочитать CSV с двумя столбцами и проверить набор ключей."""
    values = {}  # Сюда складываем пары «название настройки: значение».
    try:
        with path.open(encoding="utf-8-sig", newline="") as stream:
            reader = csv.reader(stream, strict=True)
            # Сначала проверяем, что открыли таблицу нужного устройства.
            if next(reader, None) != HEADER:
                raise ConfigError("Заголовок CSV должен быть parameter,value.")
            # CSV возвращает текст; преобразование типов выполняется позже.
            for row in reader:
                # Пустые строки не являются настройками.
                if not row:
                    continue
                # Отсекаем недостающие и лишние столбцы до распаковки.
                if len(row) != COLUMN_COUNT:
                    raise ConfigError(
                        f"Строка {reader.line_num}: нужны два столбца."
                    )
                # Пробелы по краям не должны менять название настройки.
                key, value = (cell.strip() for cell in row)
                # Неизвестные ключи и повторы могли бы скрыть опечатку.
                if key not in FIELDS:
                    raise ConfigError(f"Неизвестный параметр: {key}.")
                if key in values:
                    raise ConfigError(f"Параметр {key} указан повторно.")
                values[key] = value  # Сохраняем уже проверенную пару.
    except (OSError, UnicodeError, csv.Error) as error:
        raise ConfigError(f"Не удалось прочитать CSV: {error}") from error
    # Находим обязательные настройки, которых не оказалось в файле.
    missing = set(FIELDS) - values.keys()
    if missing:
        names = ", ".join(sorted(missing))
        raise ConfigError("Отсутствуют параметры: " + names)
    return values


def _boolean(key, value):
    """Преобразовать true/false в логическое значение."""
    # Строгое написание помогает сразу заметить ошибку вроде «yes».
    if value not in ("true", "false"):
        raise ConfigError(f"{key}: допустимы только true или false.")
    return value == "true"  # Возвращаем True/False вместо текста из CSV.


def _depth(value):
    """Прочитать неотрицательную целочисленную глубину."""
    # До преобразования исключаем слова, дроби, минус и пустое значение.
    if not re.fullmatch(r"[0-9]+", value):
        raise ConfigError("max_depth: нужно целое число от 0 и выше.")
    try:
        # Числовая глубина понадобится для сравнения во время обхода.
        result = int(value)
    except ValueError as error:
        # Python может отклонить число с чрезмерно длинной записью.
        raise ConfigError("max_depth: слишком длинное число.") from error
    # Явно закрепляем нижнюю границу допустимой глубины.
    if result < MIN_DEPTH:
        raise ConfigError("max_depth: глубина должна быть неотрицательной.")
    return result


def _repository(value, test_mode, config_path):
    """Проверить HTTP(S)-адрес или доступность локального тестового файла."""
    # Без источника данных дальнейшая загрузка невозможна.
    if not value:
        raise ConfigError("repository: укажите URL или путь к тестовому файлу.")
    # В учебном режиме источник должен быть доступным локальным файлом.
    if test_mode:
        source = Path(value)
        # Относительный путь отсчитываем от CSV, а не от папки запуска.
        if not source.is_absolute():
            source = config_path.parent / source
        try:
            # Здесь проверяем доступность файла без чтения его содержимого.
            with source.open("rb"):
                pass
        except OSError as error:
            raise ConfigError(
                "repository: тестовый файл недоступен: " + str(source)
            ) from error
        return  # Проверка файла закончена; как URL его проверять не нужно.
    # В обычном режиме проверяем интернет-адрес будущей загрузки.
    _validate_url(value)


def _validate_url(value):
    """Проверить HTTP(S)-адрес без обращения к сети."""
    try:
        # Разделяем адрес, чтобы проверить сервер, схему и порт по отдельности.
        url = urlsplit(value)
        # Проверяем запись адреса; сетевого запроса на этом этапе нет.
        valid = all((
            url.scheme in ("http", "https"), bool(url.hostname),
            url.port != 0, url.username is None, url.password is None,
            not url.fragment,
        ))
    except ValueError:
        # Например, неверно записанный порт делает весь адрес непригодным.
        valid = False
    # Пробел внутри адреса обычно означает опечатку или неверное копирование.
    if not valid or any(char.isspace() for char in value):
        raise ConfigError(
            "repository: нужен корректный URL http:// или https://."
        )


def _validate_text(values, test_mode):
    """Проверить имя пакета, запись версии и подстроку исключения."""
    # Учебные имена A, B, C проверяются иначе, чем настоящие имена Ubuntu.
    pattern = TEST_PACKAGE_PATTERN if test_mode else PACKAGE_PATTERN
    if not re.fullmatch(pattern, values["package_name"]):
        rule = "большие латинские буквы" if test_mode else "имя пакета Ubuntu"
        raise ConfigError(f"package_name: требуется {rule}.")
    # Здесь проверяем запись версии; ее наличие проверяется уже в каталоге.
    if not re.fullmatch(VERSION_PATTERN, values["package_version"]):
        raise ConfigError(
            "package_version: укажите версию с начальной цифрой, например 1.0."
        )
    # Пустой фильтр разрешен, а скрытые переводы строк и табуляции запрещены.
    if any(not char.isprintable() for char in values["filter_substring"]):
        raise ConfigError("filter_substring: управляющие символы запрещены.")


def load_config(filename):
    """Загрузить и проверить все семь параметров конфигурации."""
    path = Path(filename).resolve()
    # Сначала проверяем устройство таблицы, потом значения ее параметров.
    values = _read_rows(path)
    # Текст из CSV превращаем в переключатели и целочисленную глубину.
    test_mode = _boolean("test_mode", values["test_mode"])
    ascii_tree = _boolean("ascii_tree", values["ascii_tree"])
    depth = _depth(values["max_depth"])
    # До создания Config убеждаемся в пригодности текста и источника данных.
    _validate_text(values, test_mode)
    _repository(values["repository"], test_mode, path)
    # Остальной код получает один объект с проверенными настройками.
    return Config(
        package_name=values["package_name"],
        repository=values["repository"],
        test_mode=test_mode,
        package_version=values["package_version"],
        ascii_tree=ascii_tree,
        max_depth=depth,
        filter_substring=values["filter_substring"],
    )
