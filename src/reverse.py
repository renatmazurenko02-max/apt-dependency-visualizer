"""Обратные зависимости по всему каталогу с повторным использованием DFS."""

from .graph import build_graph
from .packages import format_dependency
from .resolver import Resolved, Resolver


class ReverseResolver(Resolver):
    """Для каждого пакета подготовить список тех, кто его требует."""

    def __init__(self, index, excluded=""):
        """Подготовить обратные переходы по всему каталогу пакетов.

        Унаследовать поиск версий, виртуальных имен и проверку фильтра.
        Учесть всех допустимых потребителей, включая другие ветки графа.
        """
        super().__init__(index, excluded)
        self.incoming = {}
        for package in index.values():
            if not self.is_excluded(package.name):
                self._record(package)

    def _record(self, parent):
        """Записать переходы от зависимостей к их потребителю parent.

        Учесть все совместимые версии и отфильтровать исключенные имена.
        Исходные требования сохранить для подписей обратных связей.
        """
        for group in parent.dependencies:
            label = format_dependency(group)
            for dependency in group:
                if self.is_excluded(dependency.name):
                    continue
                for target in self.matching(dependency):
                    if self.is_excluded(target.name):
                        continue
                    key = (target.name, target.version)
                    self.incoming.setdefault(key, []).append(
                        Resolved(parent, str(dependency), label)
                    )

    def dependencies(self, package):
        """Выдать потребителей пакета в интерфейсе обычного DFS.

        Если входящих связей нет, генератор не выдает ни одного перехода.
        """
        key = (package.name, package.version)
        yield from self.incoming.get(key, ())


def build_reverse_graph(index, root, max_depth, excluded=""):
    """Подготовить обратные переходы и вернуть построенный граф.

    Общий build_graph обрабатывает глубину, циклы и повторный обход
    по более короткому пути. reverse=True задает смысл стрелок.
    """
    resolver = ReverseResolver(index, excluded)
    graph = build_graph(index, root, max_depth, excluded, resolver)
    graph.reverse = True
    return graph
