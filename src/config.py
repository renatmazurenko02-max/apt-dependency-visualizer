"""Чтение CSV-конфигурации и проверка пользовательских параметров."""

import csv
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit


FIELDS = (
    "package_name",
    "repository",
    "test_mode",
    "package_version",
    "ascii_tree",
    "max_depth",
    "filter_substring",
)
HEADER = ["parameter", "value"]
COLUMN_COUNT = len(HEADER)
MIN_DEPTH = 0
PACKAGE_PATTERN = r"[a-z0-9][a-z0-9+.-]+"
TEST_PACKAGE_PATTERN = r"[A-Z]+"
VERSION_PATTERN = r"(?:[0-9]+:)?[0-9][A-Za-z0-9.+:~\-]*"


class ConfigError(ValueError):
    """Ошибка структуры CSV или значения параметра."""


@dataclass(frozen=True)
class Config:
    """Проверенные настройки; глубина ноль означает только корневой пакет."""

    package_name: str
    repository: str
    test_mode: bool
    package_version: str
    ascii_tree: bool
    max_depth: int
    filter_substring: str


def _read_rows(path):
    """Прочитать CSV с двумя столбцами и проверить набор ключей."""
    values = {}
    try:
        with path.open(encoding="utf-8-sig", newline="") as stream:
            reader = csv.reader(stream, strict=True)
            if next(reader, None) != HEADER:
                raise ConfigError("Заголовок CSV должен быть parameter,value.")
            for row in reader:
                if not row:
                    continue
                if len(row) != COLUMN_COUNT:
                    raise ConfigError(
                        f"Строка {reader.line_num}: нужны два столбца."
                    )
                key, value = (cell.strip() for cell in row)
                if key not in FIELDS:
                    raise ConfigError(f"Неизвестный параметр: {key}.")
                if key in values:
                    raise ConfigError(f"Параметр {key} указан повторно.")
                values[key] = value
    except (OSError, UnicodeError, csv.Error) as error:
        raise ConfigError(f"Не удалось прочитать CSV: {error}") from error
    missing = set(FIELDS) - values.keys()
    if missing:
        names = ", ".join(sorted(missing))
        raise ConfigError("Отсутствуют параметры: " + names)
    return values


def _boolean(key, value):
    """Преобразовать true/false в логическое значение."""
    if value not in ("true", "false"):
        raise ConfigError(f"{key}: допустимы только true или false.")
    return value == "true"


def _depth(value):
    """Прочитать неотрицательную целочисленную глубину."""
    if not re.fullmatch(r"[0-9]+", value):
        raise ConfigError("max_depth: нужно целое число от 0 и выше.")
    try:
        result = int(value)
    except ValueError as error:
        raise ConfigError("max_depth: слишком длинное число.") from error
    if result < MIN_DEPTH:
        raise ConfigError("max_depth: глубина должна быть неотрицательной.")
    return result


def _repository(value, test_mode, config_path):
    """Проверить HTTP(S)-адрес или доступность локального тестового файла."""
    if not value:
        raise ConfigError("repository: укажите URL или путь к тестовому файлу.")
    if test_mode:
        source = Path(value)
        if not source.is_absolute():
            source = config_path.parent / source
        try:
            with source.open("rb"):
                pass
        except OSError as error:
            raise ConfigError(
                "repository: тестовый файл недоступен: " + str(source)
            ) from error
        return
    _validate_url(value)


def _validate_url(value):
    """Проверить HTTP(S)-адрес без обращения к сети."""
    try:
        url = urlsplit(value)
        valid = all((
            url.scheme in ("http", "https"), bool(url.hostname),
            url.port != 0, url.username is None, url.password is None,
            not url.fragment,
        ))
    except ValueError:
        valid = False
    if not valid or any(char.isspace() for char in value):
        raise ConfigError(
            "repository: нужен корректный URL http:// или https://."
        )


def _validate_text(values, test_mode):
    """Проверить имя пакета, запись версии и подстроку исключения."""
    pattern = TEST_PACKAGE_PATTERN if test_mode else PACKAGE_PATTERN
    if not re.fullmatch(pattern, values["package_name"]):
        rule = "большие латинские буквы" if test_mode else "имя пакета Ubuntu"
        raise ConfigError(f"package_name: требуется {rule}.")
    if not re.fullmatch(VERSION_PATTERN, values["package_version"]):
        raise ConfigError(
            "package_version: укажите версию с начальной цифрой, например 1.0."
        )
    if any(not char.isprintable() for char in values["filter_substring"]):
        raise ConfigError("filter_substring: управляющие символы запрещены.")


def load_config(filename):
    """Загрузить и проверить все семь параметров конфигурации."""
    path = Path(filename).resolve()
    values = _read_rows(path)
    test_mode = _boolean("test_mode", values["test_mode"])
    ascii_tree = _boolean("ascii_tree", values["ascii_tree"])
    depth = _depth(values["max_depth"])
    _validate_text(values, test_mode)
    _repository(values["repository"], test_mode, path)
    return Config(
        package_name=values["package_name"],
        repository=values["repository"],
        test_mode=test_mode,
        package_version=values["package_version"],
        ascii_tree=ascii_tree,
        max_depth=depth,
        filter_substring=values["filter_substring"],
    )
