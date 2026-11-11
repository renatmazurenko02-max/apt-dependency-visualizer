"""Текстовое ASCII-дерево уже построенного графа с циклами и повторами."""


class _Tree:
    """Развернуть граф в дерево вывода, сохранив ограничения путей."""

    def __init__(self, graph, max_depth):
        """Сгруппировать связи по источнику для быстрого прохода по детям."""
        self.graph = graph
        self.max_depth = max_depth
        self.children = {}
        self.expanded = {}
        self.lines = []
        for edge in graph.edges:
            self.children.setdefault(edge.source, []).append(edge)

    def branch(self, key, prefix, connector, depth, active):
        """Добавить строку и при необходимости раскрыть следующую ветку."""
        label = "@".join(key)
        suffix = self._stop_reason(key, depth, active)
        self.lines.append(prefix + connector + label + suffix)
        if suffix:
            return
        self.expanded[key] = depth
        # Отдельный путь отличает цикл от общей зависимости разных веток.
        active = active | {key}
        children = self.children.get(key, [])
        for number, edge in enumerate(children):
            last = number == len(children) - 1
            next_prefix = prefix
            if connector:
                next_prefix += "    " if connector == "`-- " else "|   "
            self.branch(
                edge.target, next_prefix, "`-- " if last else "|-- ",
                depth + 1, active,
            )

    def _stop_reason(self, key, depth, active):
        """Объяснить остановку на цикле, границе глубины или повторе."""
        if key in active:
            return " [цикл]"
        if depth >= self.max_depth:
            return " [предел глубины]"
        previous = self.expanded.get(key)
        if previous is not None and previous <= depth:
            return " [повтор]"
        return ""


def format_tree(graph, max_depth):
    """Вернуть строки ASCII-дерева без повторного получения зависимостей."""
    if not graph.nodes:
        return ["Исходный пакет исключен фильтром."]
    tree = _Tree(graph, max_depth)
    tree.branch(graph.root, "", "", 0, set())
    return tree.lines
