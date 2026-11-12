"""Загрузка Packages средствами стандартной библиотеки Python.

TIMEOUT_SECONDS ограничивает ожидание ответа, MAX_DOWNLOAD_BYTES
и MAX_TEXT_BYTES ограничивают загруженные и распакованные данные.
INDEX_FILES задает порядок форматов, начиная со сжатых; HTTP 404
разрешает попробовать следующий формат. TEST_NAME проверяет A-Z.
"""

import bz2
import gzip
import io
import json
import lzma
import re
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from .packages import Dependency, Package, RepositoryError, parse_packages


TIMEOUT_SECONDS = 30
MAX_DOWNLOAD_BYTES = 32 * 1024 * 1024
MAX_TEXT_BYTES = 128 * 1024 * 1024
NOT_FOUND = 404
DOWNLOAD_ERRORS = (OSError, URLError, ValueError, EOFError, lzma.LZMAError)
TEST_NAME = re.compile(r"[A-Z]+")
INDEX_FILES = ("Packages.xz", "Packages.gz", "Packages.bz2", "Packages")


def _download(url):
    """Скачать файл и вернуть байты с ограничением времени и размера.

    User-Agent сообщает серверу имя программы. Прочитать на байт
    больше лимита, чтобы обнаружить превышение разрешенного размера.
    """
    request = Request(
        url, headers={"User-Agent": "apt-dependency-visualizer/2"}
    )
    with urlopen(request, timeout=TIMEOUT_SECONDS) as response:
        data = response.read(MAX_DOWNLOAD_BYTES + 1)
    if len(data) > MAX_DOWNLOAD_BYTES:
        raise RepositoryError("Каталог слишком большой для загрузки.")
    return data


def _decode(data):
    """Распаковать данные по сигнатуре и вернуть текст UTF-8.

    Первые байты определяют gzip, xz или bzip2 независимо от URL.
    Обрабатывать данные в памяти, ограничивая распакованный размер.
    Декодирование utf-8-sig также удаляет необязательный BOM.
    """
    stream = io.BytesIO(data)
    if data.startswith(b"\xfd7zXZ\x00"):
        stream = lzma.LZMAFile(stream)
    elif data.startswith(b"\x1f\x8b"):
        stream = gzip.GzipFile(fileobj=stream)
    elif data.startswith(b"BZh"):
        stream = bz2.BZ2File(stream)
    with stream:
        content = stream.read(MAX_TEXT_BYTES + 1)
    if len(content) > MAX_TEXT_BYTES:
        raise RepositoryError("Распакованный каталог слишком большой.")
    return content.decode("utf-8-sig")


def _index_urls(repository):
    """Вернуть URL индекса или варианты файлов в указанной папке.

    Точный адрес Packages оставить без изменений. Для папки построить
    адреса всех поддерживаемых форматов в порядке INDEX_FILES.
    """
    filename = urlsplit(repository).path.rsplit("/", maxsplit=1)[-1]
    if filename in INDEX_FILES:
        return (repository,)
    return tuple(repository.rstrip("/") + "/" + name for name in INDEX_FILES)


def load_remote(repository):
    """Скачать, распаковать и разобрать каталог Ubuntu в индекс.

    Перебирать варианты адресов только при HTTP 404. Прочие ошибки
    сети, распаковки и разбора сообщать через RepositoryError.
    Если ни один файл не найден, объяснить нужный формат URL.
    """
    for url in _index_urls(repository):
        try:
            return parse_packages(_decode(_download(url)))
        except HTTPError as error:
            if error.code != NOT_FOUND:
                raise RepositoryError(f"Сервер вернул HTTP {error.code}.")
        except DOWNLOAD_ERRORS as error:
            raise RepositoryError(f"Не удалось прочитать каталог: {error}")
    raise RepositoryError(
        "Каталог Packages не найден. Укажите URL Packages.xz или папки "
        "dists/ВЫПУСК/КОМПОНЕНТ/binary-АРХИТЕКТУРА/."
    )


def _test_package(name, record):
    """Проверить запись учебного JSON и вернуть объект Package.

    Проверить имя, тип записи, версию и список зависимостей.
    Использовать ту же модель данных, что и для пакетов Ubuntu.
    """
    if not TEST_NAME.fullmatch(name) or not isinstance(record, dict):
        raise RepositoryError("JSON: нужны имена A, B, C и записи-объекты.")
    version = record.get("version")
    if not isinstance(version, str) or not version.strip():
        raise RepositoryError(f"JSON: у пакета {name} нужна строка version.")
    groups = _test_dependencies(name, record.get("dependencies"))
    return Package(name, version, groups)


def _test_dependencies(name, dependencies):
    """Проверить список учебных зависимостей и вернуть группы.

    Разрешены только строковые имена из букв A-Z. Удалить повторы
    через dict.fromkeys, сохранив порядок. Каждое имя образует свою
    обязательную группу: альтернатив в учебном JSON нет.
    """
    if not isinstance(dependencies, list):
        raise RepositoryError(
            f"JSON: у пакета {name} нужен список dependencies."
        )
    if not all(isinstance(dep, str) for dep in dependencies):
        raise RepositoryError("JSON: имена зависимостей должны быть строками.")
    if not all(TEST_NAME.fullmatch(dep) for dep in dependencies):
        raise RepositoryError("JSON: имена зависимостей: большие буквы A-Z.")
    return tuple((Dependency(dep),) for dep in dict.fromkeys(dependencies))


def load_test(filename):
    """Прочитать учебный JSON и вернуть индекс (имя, версия) -> Package.

    Получить непустой словарь, проверить каждую запись и привести ее
    к общей модели каталога. Обход зависимостей здесь не выполняется.
    """
    try:
        data = json.loads(Path(filename).read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, ValueError) as error:
        raise RepositoryError(f"Не удалось прочитать учебный JSON: {error}")
    if not isinstance(data, dict) or not data:
        raise RepositoryError("JSON: нужен непустой объект с пакетами.")
    packages = [_test_package(name, record) for name, record in data.items()]
    return {(package.name, package.version): package for package in packages}


def load_repository(config, config_path):
    """Вернуть индекс из учебного JSON или сетевого каталога.

    config.test_mode выбирает источник. Относительный путь к JSON
    отсчитывается от папки config_path, как и при проверке настроек.
    """
    if not config.test_mode:
        return load_remote(config.repository)
    source = Path(config.repository)
    if not source.is_absolute():
        source = Path(config_path).resolve().parent / source
    return load_test(source)
