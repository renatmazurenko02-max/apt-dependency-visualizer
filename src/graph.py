"""Рекурсивный DFS с глубиной, фильтром и защитой от циклов.

NodeKey хранит пару (имя, версия), различая версии одного пакета.
"""

from dataclasses import dataclass, field
from typing import TypeAlias

from .packages import Package, RepositoryError
from .resolver import Resolver


NodeKey: TypeAlias = tuple[str, str]


@dataclass(frozen=True)
class Edge:
    """Направленная связь обхода между узлами source и target.

    requirement хранит исходное условие версии или виртуальное имя.
    group хранит полную группу альтернатив для подписи связи.
    В обратном режиме target зависит от source.
    """

    source: NodeKey
    target: NodeKey
    requirement: str
    group: str


@dataclass
class DependencyGraph:
    """Результат анализа для текстового вывода и визуализации.

    root задает исходный узел; nodes и edges хранят пакеты и связи.
    depths содержит минимальные найденные глубины узлов.
    cycle_edges отмечает переходы к узлам текущего рекурсивного пути.
    При reverse=True стрелка ведет от зависимости к потребителю.
    """

    root: NodeKey
    nodes: dict[NodeKey, Package] = field(default_factory=dict)
    edges: list[Edge] = field(default_factory=list)
    depths: dict[NodeKey, int] = field(default_factory=dict)
    cycle_edges: set[tuple[NodeKey, NodeKey]] = field(default_factory=set)
    reverse: bool = False


class GraphBuilder:
    """Хранить состояние одного обхода, не меняя сами записи каталога."""

    def __init__(self, index, root, max_depth, excluded, resolver=None):
        """Подготовить результат и состояние одного обхода DFS.

        resolver задает прямые или обратные переходы. active хранит узлы
        текущего пути, expanded_depth хранит глубины прежнего раскрытия,
        known_edges защищает список связей от повторов.
        """
        self.graph = DependencyGraph((root.name, root.version))
        self.resolver = resolver if resolver is not None else Resolver(
            index, excluded
        )
        self.max_depth = max_depth
        self.active = set()
        self.expanded_depth = {}
        self.known_edges = set()

    def visit(self, package, depth):
        """Посетить пакет и раскрыть его зависимости через connect.

        Сохранить минимальную глубину. Остановиться на фильтре, пределе
        глубины или цикле; при новом более коротком пути раскрыть узел
        снова. После обработки удалить узел из текущего пути active.
        """
        if self.resolver.is_excluded(package.name):
            return
        key = (package.name, package.version)
        self.graph.nodes[key] = package
        previous = self.graph.depths.get(key, depth)
        self.graph.depths[key] = min(previous, depth)
        if depth >= self.max_depth or key in self.active:
            return
        expanded = self.expanded_depth.get(key)
        if expanded is not None and expanded <= depth:
            return
        self.expanded_depth[key] = depth
        self.active.add(key)
        try:
            for resolved in self.resolver.dependencies(package):
                self.connect(key, resolved, depth)
        finally:
            self.active.remove(key)

    def connect(self, source, resolved, depth):
        """Сохранить связь и рекурсивно посетить следующий пакет.

        Замыкающую цикл связь сохранить и пометить. Проверка active
        в visit остановит повторное углубление по этой связи.
        """
        package = resolved.package
        target = (package.name, package.version)
        edge = Edge(source, target, resolved.requirement, resolved.group)
        if edge not in self.known_edges:
            self.graph.edges.append(edge)
            self.known_edges.add(edge)
        if target in self.active:
            self.graph.cycle_edges.add((source, target))
        self.visit(package, depth + 1)


def build_graph(index, root, max_depth, excluded="", resolver=None):
    """Построить граф, считая исходный пакет уровнем ноль."""
    if max_depth < 0:
        raise RepositoryError("Глубина графа должна быть неотрицательной.")
    builder = GraphBuilder(index, root, max_depth, excluded, resolver)
    try:
        builder.visit(root, 0)
    except RecursionError as error:
        raise RepositoryError(
            "Достигнут предел рекурсии Python. Уменьшите max_depth."
        ) from error
    return builder.graph


def _edge_text(edge, graph):
    """Вернуть текст связи с условием версии и отметкой цикла.

    При обратном поиске условие по-прежнему относится к зависимости,
    поэтому ее имя берется из source, а при прямом поиске из target.
    """
    source = "@".join(edge.source)
    target = "@".join(edge.target)
    text = f"  {source} -> {target}"
    dependency_name = edge.source[0] if graph.reverse else edge.target[0]
    if edge.requirement != dependency_name:
        text += " [" + edge.requirement + "]"
    if "|" in edge.group:
        text += " [варианты: " + edge.group + "]"
    if (edge.source, edge.target) in graph.cycle_edges:
        text += " [цикл]"
    return text


def format_graph(graph):
    """Вернуть заголовок, список узлов и список связей графа.

    Порядок словаря nodes сохраняет порядок первого посещения в DFS.
    Для исключенного корня вернуть пояснение о пустом графе.
    """
    title = "Обратные зависимости" if graph.reverse else "Граф зависимостей"
    lines = [f"{title} {graph.root[0]} (версия {graph.root[1]}):"]
    if graph.reverse:
        lines.append("Стрелка X -> Y означает: пакет Y зависит от X.")
    if not graph.nodes:
        return lines + ["Исходный пакет исключен фильтром."]
    lines.append(f"Узлы ({len(graph.nodes)}):")
    for key in graph.nodes:
        lines.append(f"  {'@'.join(key)}, глубина {graph.depths[key]}")
    lines.append(f"Связи ({len(graph.edges)}):")
    lines.extend(_edge_text(edge, graph) for edge in graph.edges)
    return lines
