"""Подбор записей каталога для продолжения обхода зависимостей."""

from dataclasses import dataclass

from .packages import Package, RepositoryError, format_dependency
from .versions import compare_versions, satisfies


@dataclass(frozen=True)
class Resolved:
    """Найденный пакет и исходное требование перехода к нему.

    package хранит реальную запись следующего пакета обхода.
    requirement сохраняет условие версии или виртуальное имя.
    group содержит полную группу альтернатив для подписи связи.
    """

    package: Package
    requirement: str
    group: str


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
        """Вернуть все записи, удовлетворяющие одной альтернативе.

        Проверить настоящее имя и поставщиков из Provides. Для обратного
        поиска сохранить все совместимые версии, затем удалить повторы.
        """
        candidates = [
            package for package in self.packages.get(dependency.name, [])
            if satisfies(package.version, dependency)
        ]
        for package, provided in self.providers.get(dependency.name, []):
            if not dependency.relation:
                candidates.append(package)
            elif provided.version and satisfies(provided.version, dependency):
                candidates.append(package)
        unique = {(item.name, item.version): item for item in candidates}
        return list(unique.values())

    def _candidates(self, dependency):
        """Выбрать версии для обычного прямого обхода."""
        return self._newest(self.matching(dependency))

    def _newest(self, candidates):
        """Выбрать новейшую подходящую версию каждого настоящего имени.

        Результат отсортировать по именам для воспроизводимого обхода.
        """
        chosen = {}
        for package in candidates:
            previous = chosen.get(package.name)
            if previous is None:
                chosen[package.name] = package
            elif compare_versions(package.version, previous.version) > 0:
                chosen[package.name] = package
        return [chosen[name] for name in sorted(chosen)]

    def resolve_group(self, group):
        """Вернуть доступные альтернативы как возможные связи графа.

        Применить фильтр к требованиям и найденным поставщикам. Если
        допустимые требования есть, но ничего не найдено, вызвать ошибку.
        Полностью исключенная ветка не считается отсутствующим пакетом.
        """
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
        if allowed and not had_candidates:
            raise RepositoryError(
                "Не найдена подходящая зависимость: " + label
            )
        return resolved

    def dependencies(self, package):
        """Получить записи для всех обязательных групп данного пакета."""
        for group in package.dependencies:
            yield from self.resolve_group(group)
