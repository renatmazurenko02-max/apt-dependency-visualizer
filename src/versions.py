"""Собственное сравнение версий Debian/Ubuntu без dpkg или apt.

PARTS выделяет чередующиеся текстовые и числовые участки.
SYMBOL_OFFSET ставит остальные знаки после букв при сравнении.
"""

import re
from itertools import zip_longest

from .packages import RepositoryError


PARTS = re.compile(r"([^0-9]*)([0-9]*)")
SYMBOL_OFFSET = 256


def _sign(value):
    """Свести результат сравнения к -1, 0 или 1."""
    return (value > 0) - (value < 0)


def _number(left, right):
    """Сравнить числовые записи, вернув -1, 0 или 1.

    Удалить ведущие нули, сравнить длины, затем цифры при равной длине.
    Преобразование в int не требуется даже для очень длинных записей.
    """
    left = left.lstrip("0")
    right = right.lstrip("0")
    if len(left) != len(right):
        return _sign(len(left) - len(right))
    return (left > right) - (left < right)


def _order(char):
    """Задать порядок: тильда, конец текста, буквы, остальные знаки."""
    if char == "~":
        return -1
    if not char:
        return 0
    if char.isalpha():
        return ord(char)
    return ord(char) + SYMBOL_OFFSET


def _letters(left, right):
    """Сравнить текстовые части с особыми правилами для тильды и знаков.

    Недостающий символ заменить пустой строкой, обозначающей конец.
    Порядок каждого символа определяет функция _order.
    """
    for first, second in zip_longest(left, right, fillvalue=""):
        difference = _order(first) - _order(second)
        if difference:
            return _sign(difference)
    return 0


def _part(left, right):
    """По очереди сравнить текстовые и числовые участки версии."""
    first = [item for item in PARTS.findall(left) if any(item)]
    second = [item for item in PARTS.findall(right) if any(item)]
    for one, two in zip_longest(first, second, fillvalue=("", "")):
        difference = _letters(one[0], two[0]) or _number(one[1], two[1])
        if difference:
            return difference
    return 0


def _split(version):
    """Разделить версию на эпоху, основную часть и ревизию Debian."""
    epoch, separator, remaining = version.partition(":")
    if not separator:
        epoch, remaining = "0", version
    if not re.fullmatch(r"[0-9]+", epoch):
        raise RepositoryError("Неверная эпоха версии: " + version)
    upstream, separator, revision = remaining.rpartition("-")
    if not separator:
        upstream, revision = remaining, "0"
    if not upstream or not upstream[0].isdigit():
        raise RepositoryError("Неверная версия: " + version)
    return epoch, upstream, revision


def compare_versions(left, right):
    """Сравнить полные версии и вернуть -1, 0 или 1.

    Сначала сравнить эпоху, затем основную часть, затем ревизию.
    Например, 1.10 новее 1.9, а 1~rc старее 1.
    """
    first = _split(left)
    second = _split(right)
    return (
        _number(first[0], second[0])
        or _part(first[1], second[1])
        or _part(first[2], second[2])
    )


def satisfies(version, dependency):
    """Проверить соответствие версии условию одной зависимости.

    Без оператора подходит любая версия. Допустимость оператора
    заранее проверяет парсер зависимости.
    """
    if not dependency.relation:
        return True
    result = compare_versions(version, dependency.version)
    return {
        "<<": result < 0, "<=": result <= 0, "=": result == 0,
        ">=": result >= 0, ">>": result > 0,
    }[dependency.relation]
