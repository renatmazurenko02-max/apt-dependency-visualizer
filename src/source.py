"""Загрузка Packages стандартной библиотекой без apt и готовых парсеров."""

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
    """Скачать один файл с ограничением времени и размера."""
    request = Request(
        url, headers={"User-Agent": "apt-dependency-visualizer/2"}
    )
    with urlopen(request, timeout=TIMEOUT_SECONDS) as response:
        data = response.read(MAX_DOWNLOAD_BYTES + 1)
    if len(data) > MAX_DOWNLOAD_BYTES:
        raise RepositoryError("Каталог слишком большой для загрузки.")
    return data


def _decode(data):
    """Распаковать gzip/xz/bzip2 по сигнатуре и прочитать UTF-8."""
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
    """Принять точный URL индекса или папку binary-ARCH с индексами."""
    filename = urlsplit(repository).path.rsplit("/", maxsplit=1)[-1]
    if filename in INDEX_FILES:
        return (repository,)
    return tuple(repository.rstrip("/") + "/" + name for name in INDEX_FILES)


def load_remote(repository):
    """Загрузить и разобрать индекс Ubuntu; при 404 попробовать иной формат."""
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
    """Проверить одну запись учебного JSON и создать пакет."""
    if not TEST_NAME.fullmatch(name) or not isinstance(record, dict):
        raise RepositoryError("JSON: нужны имена A, B, C и записи-объекты.")
    version = record.get("version")
    if not isinstance(version, str) or not version.strip():
        raise RepositoryError(f"JSON: у пакета {name} нужна строка version.")
    groups = _test_dependencies(name, record.get("dependencies"))
    return Package(name, version, groups)


def _test_dependencies(name, dependencies):
    """Проверить список учебных зависимостей и убрать повторения имен."""
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
    """Прочитать учебный граф из JSON, не обходя его зависимости."""
    try:
        data = json.loads(Path(filename).read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, ValueError) as error:
        raise RepositoryError(f"Не удалось прочитать учебный JSON: {error}")
    if not isinstance(data, dict) or not data:
        raise RepositoryError("JSON: нужен непустой объект с пакетами.")
    packages = [_test_package(name, record) for name, record in data.items()]
    return {(package.name, package.version): package for package in packages}


def load_repository(config, config_path):
    """Выбрать учебный файл или сетевой индекс по настройке test_mode."""
    if not config.test_mode:
        return load_remote(config.repository)
    # Как и при проверке, отсчитываем путь от расположения CSV.
    source = Path(config.repository)
    if not source.is_absolute():
        source = Path(config_path).resolve().parent / source
    return load_test(source)
