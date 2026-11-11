"""Обратные зависимости по всему каталогу с повторным использованием DFS."""

from .graph import build_graph
from .packages import format_dependency
from .resolver import Resolved, Resolver


class ReverseResolver(Resolver):
    """Для каждого пакета подготовить список тех, кто его требует."""

    def __init__(self, index, excluded=""):
        """Просмотреть весь каталог, чтобы не потерять другие ветки."""
        # Наследуем поиск версий, виртуальных имен и проверку фильтра.
        super().__init__(index, excluded)
        self.incoming = {}
        for package in index.values():
            if not self.is_excluded(package.name):
                self._record(package)

    def _record(self, parent):
        """Для каждой связи parent -> dependency записать обратный переход."""
        for group in parent.dependencies:
            label = format_dependency(group)
            for dependency in group:
                if self.is_excluded(dependency.name):
                    continue
                # Любая совместимая версия может иметь обратные зависимости.
                for target in self.matching(dependency):
                    if self.is_excluded(target.name):
                        continue
                    key = (target.name, target.version)
                    # Из зависимости переходим к пакету, которому она нужна.
                    self.incoming.setdefault(key, []).append(
                        Resolved(parent, str(dependency), label)
                    )

    def dependencies(self, package):
        """Вернуть обратные переходы в интерфейсе, знакомом нашему DFS."""
        key = (package.name, package.version)
        # Нет входящих связей: этот пакет никто не требует в данном каталоге.
        yield from self.incoming.get(key, ())


def build_reverse_graph(index, root, max_depth, excluded=""):
    """Развернуть переходы и применить алгоритм обхода предыдущего этапа."""
    resolver = ReverseResolver(index, excluded)
    # Глубина, циклы и повторные короткие пути обрабатываются тем же DFS.
    graph = build_graph(index, root, max_depth, excluded, resolver)
    graph.reverse = True
    return graph
