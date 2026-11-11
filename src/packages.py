"""Собственный разбор записей Packages и прямых зависимостей Ubuntu."""

# Шаблоны помогают разобрать текст, dataclass хранит результат разбора.
import re
from dataclasses import dataclass


# Именованные части шаблона отдельно извлекают имя, архитектуру и версию.
DEPENDENCY_PATTERN = re.compile(
    r"(?P<name>[a-z0-9][a-z0-9+.-]*)"
    r"(?::(?P<qualifier>[a-z0-9-]+))?"
    r"(?:\s*\(\s*(?P<relation><<|<=|=|>=|>>)"
    r"\s*(?P<version>[^()\s]+)\s*\))?"
)
FIELD_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9-]*")  # Имя поля каталога.


class RepositoryError(ValueError):
    """Ошибка загрузки, формата каталога или поиска пакета."""


@dataclass(frozen=True)
class Dependency:
    """Имя зависимости с необязательным условием версии и архитектурой."""

    name: str  # Имя нужного пакета, например libc6.
    qualifier: str = ""  # Уточнение после двоеточия, например any или native.
    relation: str = ""  # Условие сравнения версий: >=, =, << и т.д.
    version: str = ""  # Версия, с которой нужно сравнивать.

    def __str__(self):
        """Вернуть читаемую запись зависимости, сохранив ограничения."""
        name = self.name
        # Восстанавливаем уточнение и условие для понятного вывода пользователю.
        if self.qualifier:
            name += ":" + self.qualifier
        if self.relation:
            name += f" ({self.relation} {self.version})"
        return name


@dataclass(frozen=True)
class Package:
    """Пакет; внутри каждой группы достаточно одной из альтернатив."""

    name: str  # Название пакета из поля Package.
    version: str  # Точная версия из поля Version.
    # Например, ((A, B), (C,)) означает: нужен A или B, а также нужен C.
    dependencies: tuple[tuple[Dependency, ...], ...]


def _add_field(record, line, previous, number):
    """Добавить поле записи или продолжение предыдущего поля."""
    # Строка с отступом продолжает значение предыдущего поля.
    if line.startswith((" ", "\t")):
        if previous is None:
            raise RepositoryError(f"Packages: лишний отступ в строке {number}.")
        record[previous] += " " + line.strip()
        return previous
    # Делим только по первому двоеточию: в самой версии оно тоже бывает.
    key, separator, value = line.partition(":")
    if not separator or not FIELD_PATTERN.fullmatch(key):
        raise RepositoryError(f"Packages: неверное поле в строке {number}.")
    # Повторенное поле делает запись неоднозначной, поэтому это ошибка.
    if key in record:
        raise RepositoryError(f"Packages: поле {key} повторено в записи.")
    record[key] = value.strip()
    return key


def iter_records(text):
    """Разделить каталог на записи; учесть переносы длинных полей."""
    record = {}  # Поля текущего пакета.
    previous = None  # Поле, к которому можно присоединить строку с отступом.
    for number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            # Пустая строка отделяет один пакет от следующего.
            if record:
                yield record  # Передаем готовую запись вызывающему циклу.
            record = {}
            previous = None
        else:
            previous = _add_field(record, line, previous, number)
    # Последняя запись может не иметь пустой строки в конце файла.
    if record:
        yield record


def _parse_dependency(text):
    """Разобрать одну зависимость без потери версии и квалификатора."""
    # Разбираем одну альтернативу, например libc6 (>= 2.34).
    match = DEPENDENCY_PATTERN.fullmatch(text.strip())
    if match is None:
        raise RepositoryError("Неподдерживаемая запись зависимости: " + text)
    # Имена частей шаблона совпадают с полями модели Dependency.
    # Отсутствующие необязательные части заменяем пустыми строками.
    return Dependency(**{
        key: value or "" for key, value in match.groupdict().items()
    })


def parse_dependencies(text):
    """Запятые разделяют обязательные группы, вертикальные черты: выбор."""
    # Пакет без Depends не имеет объявленных зависимостей этого типа.
    if not text.strip():
        return ()
    # A | B остается одной группой; не выдаем ее за две обязательные связи.
    return tuple(
        tuple(_parse_dependency(part) for part in group.split("|"))
        for group in text.split(",")
    )


def parse_packages(text):
    """Построить индекс по паре (имя, версия) из текста Packages."""
    index = {}  # Быстрый поиск: (имя, версия) -> объект Package.
    for record in iter_records(text):
        if not record.get("Package") or not record.get("Version"):
            raise RepositoryError("Packages: нужны поля Package и Version.")
        # Берем обязательные зависимости из обоих полей, без рекомендаций.
        dependencies = parse_dependencies(record.get("Pre-Depends", ""))
        dependencies += parse_dependencies(record.get("Depends", ""))
        package = Package(record["Package"], record["Version"], dependencies)
        # Одно имя может иметь несколько версий, поэтому ключ составной.
        key = (package.name, package.version)
        if key in index:
            raise RepositoryError(
                "Packages: повтор пакета и версии: " + str(key)
            )
        index[key] = package
    # Пустой ответ сервера не должен выглядеть как успешный результат.
    if not index:
        raise RepositoryError("Packages: каталог пакетов пуст.")
    return index


def find_package(index, name, version):
    """Найти именно запрошенную версию, не подменяя ее другой."""
    # Точное совпадение защищает от случайного выбора другой версии.
    key = (name, version)
    if key in index:
        return index[key]
    # Для ошибки различаем отсутствующее имя и отсутствующую версию.
    versions = sorted(ver for pkg, ver in index if pkg == name)
    if not versions:
        raise RepositoryError(f"Пакет {name} не найден в выбранном каталоге.")
    available = ", ".join(versions)  # Доступные версии для подсказки.
    raise RepositoryError(
        f"Версия {version} пакета {name} не найдена. Доступны: {available}"
    )


def format_dependency(group):
    """Отобразить альтернативы одной обязательной группы."""
    # Вертикальная черта показывает выбор, а не необходимость всех вариантов.
    return " | ".join(str(dependency) for dependency in group)
