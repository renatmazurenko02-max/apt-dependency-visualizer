"""Собственное сравнение версий Debian/Ubuntu без вызова dpkg или apt."""

import re
from itertools import zip_longest

from .packages import RepositoryError


# Чередуем текстовые и числовые части; числа сравниваются по значению.
PARTS = re.compile(r"([^0-9]*)([0-9]*)")
SYMBOL_OFFSET = 256  # Знаки после букв в порядке сравнения Debian.


def _sign(value):
    """Свести результат сравнения к -1, 0 или 1."""
    return (value > 0) - (value < 0)


def _number(left, right):
    """Сравнить числовые записи без переполнения и влияния ведущих нулей."""
    left = left.lstrip("0")
    right = right.lstrip("0")
    # Сначала длина, а при равной длине обычный порядок цифр.
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
    """Сравнить текстовые части с особыми правилами для ~ и знаков."""
    # Недостающий символ заменяем концом текста, у которого свой порядок.
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
    """Сравнить полные версии; например, 1.10 новее 1.9, а 1~rc старее 1."""
    first = _split(left)
    second = _split(right)
    # Эпоха важнее основной части, основная часть важнее ревизии.
    return (
        _number(first[0], second[0])
        or _part(first[1], second[1])
        or _part(first[2], second[2])
    )


def satisfies(version, dependency):
    """Проверить, удовлетворяет ли версия условию одной зависимости."""
    if not dependency.relation:
        return True
    result = compare_versions(version, dependency.version)
    # Операторы уже проверены парсером записи зависимости.
    return {
        "<<": result < 0, "<=": result <= 0, "=": result == 0,
        ">=": result >= 0, ">>": result > 0,
    }[dependency.relation]
