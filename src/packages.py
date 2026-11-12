"""Собственный разбор записей Packages и зависимостей Ubuntu.

DEPENDENCY_PATTERN извлекает имя, квалификатор и условие версии.
FIELD_PATTERN проверяет имена полей каталога. Модели dataclass
хранят полученные пакеты и зависимости.
"""

import re
from dataclasses import dataclass


DEPENDENCY_PATTERN = re.compile(
    r"(?P<name>[a-z0-9][a-z0-9+.-]*)"
    r"(?::(?P<qualifier>[a-z0-9-]+))?"
    r"(?:\s*\(\s*(?P<relation><<|<=|=|>=|>>)"
    r"\s*(?P<version>[^()\s]+)\s*\))?"
)
FIELD_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9-]*")


class RepositoryError(ValueError):
    """Ошибка загрузки, формата каталога или поиска пакета."""


@dataclass(frozen=True)
class Dependency:
    """Одна альтернатива зависимости с необязательным условием версии.

    Атрибуты:
        name: Имя требуемого пакета, например libc6.
        qualifier: Уточнение после двоеточия, например any или native.
        relation: Оператор сравнения версий, например >= или =.
        version: Версия, с которой сравнивается найденный пакет.
    """

    name: str
    qualifier: str = ""
    relation: str = ""
    version: str = ""

    def __str__(self):
        """Вернуть имя с квалификатором и условием версии, если они заданы."""
        name = self.name
        if self.qualifier:
            name += ":" + self.qualifier
        if self.relation:
            name += f" ({self.relation} {self.version})"
        return name


@dataclass(frozen=True)
class Package:
    """Запись пакета с версией, группами зависимостей и Provides.

    name и version берутся из полей Package и Version каталога.
    dependencies хранит обязательные группы; внутри каждой достаточно
    одной альтернативы. ((A, B), (C,)) означает: A или B, а также C.
    provides перечисляет виртуальные имена, предоставляемые пакетом.
    """

    name: str
    version: str
    dependencies: tuple[tuple[Dependency, ...], ...]
    provides: tuple[Dependency, ...] = ()


def _add_field(record, line, previous, number):
    """Добавить поле в record и вернуть имя текущего поля.

    Строку с отступом присоединить к previous. Новое поле разделить
    по первому двоеточию, сохранив двоеточия внутри значения.
    Повтор поля, неверное имя или лишний отступ считать ошибкой.
    """
    if line.startswith((" ", "\t")):
        if previous is None:
            raise RepositoryError(f"Packages: лишний отступ в строке {number}.")
        record[previous] += " " + line.strip()
        return previous
    key, separator, value = line.partition(":")
    if not separator or not FIELD_PATTERN.fullmatch(key):
        raise RepositoryError(f"Packages: неверное поле в строке {number}.")
    if key in record:
        raise RepositoryError(f"Packages: поле {key} повторено в записи.")
    record[key] = value.strip()
    return key


def iter_records(text):
    """Последовательно выдавать словари полей пакетов из Packages.

    Пустая строка завершает запись. previous указывает поле для строки
    с отступом. Последнюю запись выдать и без пустой строки в конце.
    """
    record = {}
    previous = None
    for number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            if record:
                yield record
            record = {}
            previous = None
        else:
            previous = _add_field(record, line, previous, number)
    if record:
        yield record


def _parse_dependency(text):
    """Разобрать одну альтернативу, например libc6 (>= 2.34).

    Именованные группы шаблона передать в Dependency; отсутствующие
    квалификатор и условие версии заменить пустыми строками.
    """
    match = DEPENDENCY_PATTERN.fullmatch(text.strip())
    if match is None:
        raise RepositoryError("Неподдерживаемая запись зависимости: " + text)
    return Dependency(**{
        key: value or "" for key, value in match.groupdict().items()
    })


def parse_dependencies(text):
    """Вернуть обязательные группы зависимостей из текста поля.

    Запятые разделяют группы, символ | разделяет альтернативы внутри
    группы. Пустой текст означает отсутствие зависимостей этого типа.
    """
    if not text.strip():
        return ()
    return tuple(
        tuple(_parse_dependency(part) for part in group.split("|"))
        for group in text.split(",")
    )


def parse_packages(text):
    """Вернуть индекс (имя, версия) -> Package из текста Packages.

    Объединить Pre-Depends и Depends, сохранив группы альтернатив.
    Из Provides получить виртуальные имена пакетов. Отклонить пустой
    каталог, пропуск обязательных полей и повтор одной пары ключей.
    """
    index = {}
    for record in iter_records(text):
        if not record.get("Package") or not record.get("Version"):
            raise RepositoryError("Packages: нужны поля Package и Version.")
        dependencies = parse_dependencies(record.get("Pre-Depends", ""))
        dependencies += parse_dependencies(record.get("Depends", ""))
        provides = tuple(
            item for group in parse_dependencies(record.get("Provides", ""))
            for item in group
        )
        package = Package(
            record["Package"], record["Version"], dependencies, provides
        )
        key = (package.name, package.version)
        if key in index:
            raise RepositoryError(
                "Packages: повтор пакета и версии: " + str(key)
            )
        index[key] = package
    if not index:
        raise RepositoryError("Packages: каталог пакетов пуст.")
    return index


def find_package(index, name, version):
    """Вернуть пакет с точным совпадением имени и версии.

    При отсутствии имени вызвать RepositoryError. При отсутствии
    версии дополнить ошибку списком доступных версий этого пакета.
    """
    key = (name, version)
    if key in index:
        return index[key]
    versions = sorted(ver for pkg, ver in index if pkg == name)
    if not versions:
        raise RepositoryError(f"Пакет {name} не найден в выбранном каталоге.")
    available = ", ".join(versions)
    raise RepositoryError(
        f"Версия {version} пакета {name} не найдена. Доступны: {available}"
    )


def format_dependency(group):
    """Соединить альтернативы группы символом |, обозначающим выбор."""
    return " | ".join(str(dependency) for dependency in group)
