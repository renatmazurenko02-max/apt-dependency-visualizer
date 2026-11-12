"""Рекурсивный DFS с ограничением глубины, фильтром и защитой от циклов."""

from dataclasses import dataclass, field
from typing import TypeAlias

from .packages import Package, RepositoryError
from .resolver import Resolver


# Одно имя может иметь разные версии, поэтому узел задаем парой значений.
NodeKey: TypeAlias = tuple[str, str]


@dataclass(frozen=True)
class Edge:
    """Направленная связь обхода; ее смысл зависит от режима графа."""

    source: NodeKey
    target: NodeKey
    requirement: str  # Условие версии или виртуальное имя из каталога.
    group: str  # Альтернативы сохраняются, чтобы не исказить их смысл.


@dataclass
class DependencyGraph:
    """Результат анализа, который позднее будет передан визуализатору."""

    root: NodeKey
    nodes: dict[NodeKey, Package] = field(default_factory=dict)
    edges: list[Edge] = field(default_factory=list)
    depths: dict[NodeKey, int] = field(default_factory=dict)
    # Здесь отмечаются переходы назад к пакету текущего рекурсивного пути.
    cycle_edges: set[tuple[NodeKey, NodeKey]] = field(default_factory=set)
    reverse: bool = False  # В обратном режиме цель зависит от источника.


class GraphBuilder:
    """Хранить состояние одного обхода, не меняя сами записи каталога."""

    def __init__(self, index, root, max_depth, excluded, resolver=None):
        """Подготовить результат и отдельные наборы для контроля обхода."""
        self.graph = DependencyGraph((root.name, root.version))
        # Другой источник переходов позволяет повторно использовать тот же DFS.
        self.resolver = resolver if resolver is not None else Resolver(
            index, excluded
        )
        self.max_depth = max_depth
        self.active = set()  # Только пакеты текущего рекурсивного пути.
        self.expanded_depth = {}  # На какой глубине раскрывали каждый пакет.
        self.known_edges = set()  # Общие зависимости не дублируют связи.

    def visit(self, package, depth):
        """Обойти пакет; рекурсивный вызов для его зависимостей в connect."""
        if self.resolver.is_excluded(package.name):
            return
        key = (package.name, package.version)
        self.graph.nodes[key] = package
        # Один пакет может быть достигнут разными путями, берем кратчайший.
        previous = self.graph.depths.get(key, depth)
        self.graph.depths[key] = min(previous, depth)
        if depth >= self.max_depth or key in self.active:
            return
        expanded = self.expanded_depth.get(key)
        if expanded is not None and expanded <= depth:
            return
        # Более короткий новый путь позволяет раскрыть еще часть зависимостей.
        self.expanded_depth[key] = depth
        self.active.add(key)
        try:
            for resolved in self.resolver.dependencies(package):
                self.connect(key, resolved, depth)
        finally:
            self.active.remove(key)

    def connect(self, source, resolved, depth):
        """Сохранить связь и рекурсивно перейти к пакету следующего уровня."""
        package = resolved.package
        target = (package.name, package.version)
        edge = Edge(source, target, resolved.requirement, resolved.group)
        if edge not in self.known_edges:
            self.graph.edges.append(edge)
            self.known_edges.add(edge)
        # Связь цикла остается в графе, повторное углубление будет остановлено.
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
    """Показать связь, исходное условие и отметку замыкания цикла."""
    source = "@".join(edge.source)
    target = "@".join(edge.target)
    text = f"  {source} -> {target}"
    # Исходное условие относится к зависимости, даже если стрелка развернута.
    dependency_name = edge.source[0] if graph.reverse else edge.target[0]
    if edge.requirement != dependency_name:
        text += " [" + edge.requirement + "]"
    if "|" in edge.group:
        text += " [варианты: " + edge.group + "]"
    if (edge.source, edge.target) in graph.cycle_edges:
        text += " [цикл]"
    return text


def format_graph(graph):
    """Получить список строк для демонстрации графа в терминале."""
    title = "Обратные зависимости" if graph.reverse else "Граф зависимостей"
    lines = [f"{title} {graph.root[0]} (версия {graph.root[1]}):"]
    if graph.reverse:
        lines.append("Стрелка X -> Y означает: пакет Y зависит от X.")
    if not graph.nodes:
        return lines + ["Исходный пакет исключен фильтром."]
    lines.append(f"Узлы ({len(graph.nodes)}):")
    # Порядок словаря сохраняет порядок первого посещения узлов DFS.
    for key in graph.nodes:
        lines.append(f"  {'@'.join(key)}, глубина {graph.depths[key]}")
    lines.append(f"Связи ({len(graph.edges)}):")
    lines.extend(_edge_text(edge, graph) for edge in graph.edges)
    return lines
