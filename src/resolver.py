"""Подбор записей каталога для продолжения обхода зависимостей."""

from dataclasses import dataclass

from .packages import Package, RepositoryError, format_dependency
from .versions import compare_versions, satisfies


@dataclass(frozen=True)
class Resolved:
    """Найденный пакет и исходное условие, которое привело к нему."""

    package: Package  # Настоящий пакет следующего шага обхода.
    requirement: str  # Исходная запись, включая версию и виртуальное имя.
    group: str  # Полная группа альтернатив для подписи связи в графе.


class Resolver:
    """Искать подходящие версии и поставщиков виртуальных пакетов."""

    def __init__(self, index, excluded=""):
        """Один раз сгруппировать записи, чтобы не сканировать весь каталог."""
        self.excluded = excluded
        self.packages = {}
        self.providers = {}
        for package in index.values():
            self.packages.setdefault(package.name, []).append(package)
            for provided in package.provides:
                self.providers.setdefault(provided.name, []).append(
                    (package, provided)
                )

    def is_excluded(self, name):
        """Проверить буквальное вхождение подстроки с учетом регистра."""
        return bool(self.excluded) and self.excluded in name

    def matching(self, dependency):
        """Найти все записи, удовлетворяющие одной альтернативе."""
        candidates = [
            package for package in self.packages.get(dependency.name, [])
            if satisfies(package.version, dependency)
        ]
        # Виртуальная зависимость может выполняться другим именем пакета.
        for package, provided in self.providers.get(dependency.name, []):
            if not dependency.relation:
                candidates.append(package)
            elif provided.version and satisfies(provided.version, dependency):
                candidates.append(package)
        # Для обратного поиска важны все совместимые версии, не только новая.
        unique = {(item.name, item.version): item for item in candidates}
        return list(unique.values())

    def _candidates(self, dependency):
        """Выбрать версии для обычного прямого обхода."""
        return self._newest(self.matching(dependency))

    def _newest(self, candidates):
        """Выбрать новейшую подходящую версию каждого настоящего имени."""
        chosen = {}
        for package in candidates:
            previous = chosen.get(package.name)
            if previous is None:
                chosen[package.name] = package
            elif compare_versions(package.version, previous.version) > 0:
                chosen[package.name] = package
        # Сортировка имен делает выбор поставщиков воспроизводимым.
        return [chosen[name] for name in sorted(chosen)]

    def resolve_group(self, group):
        """Сохранить все доступные альтернативы как возможные связи графа."""
        resolved = []
        had_candidates = False
        allowed = [dep for dep in group if not self.is_excluded(dep.name)]
        label = format_dependency(group)
        for dependency in allowed:
            candidates = self._candidates(dependency)
            had_candidates = had_candidates or bool(candidates)
            for package in candidates:
                if not self.is_excluded(package.name):
                    resolved.append(Resolved(package, str(dependency), label))
        # Отсеченная фильтром ветка не считается отсутствующей зависимостью.
        if allowed and not had_candidates:
            raise RepositoryError(
                "Не найдена подходящая зависимость: " + label
            )
        return resolved

    def dependencies(self, package):
        """Получить записи для всех обязательных групп данного пакета."""
        for group in package.dependencies:
            yield from self.resolve_group(group)
