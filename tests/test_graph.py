"""Проверки рекурсивного обхода на небольших понятных графах."""

import unittest

from src.graph import build_graph, format_graph
from src.packages import Dependency, Package, RepositoryError


def make_index(connections):
    """Создать учебный каталог из словаря вида A: [B, C]."""
    return {
        (name, "1.0"): Package(
            name, "1.0", tuple((Dependency(dep),) for dep in dependencies)
        )
        for name, dependencies in connections.items()
    }


class GraphTests(unittest.TestCase):
    """Проверить глубину, фильтрацию, общие зависимости и циклы."""

    def graph(self, connections, depth=5, excluded=""):
        """Построить граф учебного пакета A с выбранными настройками."""
        index = make_index(connections)
        return build_graph(index, index[("A", "1.0")], depth, excluded)

    def test_dfs_order(self):
        """Сначала полностью проходим ветку B, затем переходим к C."""
        graph = self.graph({"A": ["B", "C"], "B": ["D"], "C": [], "D": []})
        self.assertEqual([key[0] for key in graph.nodes], ["A", "B", "D", "C"])
        self.assertEqual(len(graph.edges), 3)

    def test_depth_boundaries(self):
        """Корень имеет глубину 0; каждый переход увеличивает ее на один."""
        connections = {"A": ["B"], "B": ["C"], "C": []}
        for depth, names in [(0, ["A"]), (1, ["A", "B"]), (2, ["A", "B", "C"])]:
            with self.subTest(depth=depth):
                graph = self.graph(connections, depth)
                self.assertEqual([key[0] for key in graph.nodes], names)
                self.assertTrue(all(
                    value <= depth for value in graph.depths.values()
                ))

    def test_cycle_preserves_closing_edge(self):
        """Обход цикла завершается и сохраняет замыкающую связь."""
        graph = self.graph({"A": ["B"], "B": ["C"], "C": ["A"]})
        self.assertEqual(len(graph.nodes), 3)
        self.assertEqual(len(graph.edges), 3)
        self.assertIn((("C", "1.0"), ("A", "1.0")), graph.cycle_edges)
        self.assertIn("[цикл]", "\n".join(format_graph(graph)))

    def test_self_dependency(self):
        """Пакет, зависящий от себя, остается одним узлом с петлей."""
        graph = self.graph({"A": ["A"]})
        self.assertEqual(len(graph.nodes), 1)
        self.assertEqual(len(graph.edges), 1)
        self.assertTrue(graph.cycle_edges)

    def test_shorter_path_reopens_boundary_node(self):
        """После длинного пути короткий позволяет раскрыть еще один уровень."""
        graph = self.graph({
            "A": ["B", "C"], "B": ["D"], "D": ["E"],
            "C": ["E"], "E": ["F"], "F": [],
        }, depth=3)
        self.assertEqual(graph.depths[("E", "1.0")], 2)
        self.assertEqual(graph.depths[("F", "1.0")], 3)
        self.assertEqual(len(graph.nodes), 6)
        self.assertEqual(len(graph.edges), 6)

    def test_shared_node_is_not_cycle(self):
        """Общая зависимость двух веток не означает наличие цикла."""
        graph = self.graph({
            "A": ["B", "C"], "B": ["D"], "C": ["D"], "D": [],
        })
        self.assertEqual(len(graph.nodes), 4)
        self.assertEqual(len(graph.edges), 4)
        self.assertFalse(graph.cycle_edges)

    def test_filter_keeps_other_route(self):
        """Исключаем B и BB, но D достижим по оставшемуся пути через C."""
        graph = self.graph({
            "A": ["B", "BB", "C"], "B": ["D"], "BB": ["E"],
            "C": ["D"], "D": [], "E": [],
        }, excluded="B")
        self.assertEqual([key[0] for key in graph.nodes], ["A", "C", "D"])

    def test_filtered_root(self):
        """Исключение исходного пакета дает пустой граф с пояснением."""
        graph = self.graph({"A": ["B"], "B": []}, excluded="A")
        self.assertFalse(graph.nodes)
        self.assertFalse(graph.edges)
        self.assertIn("исключен фильтром", "\n".join(format_graph(graph)))

    def test_missing_dependency(self):
        """Отсутствующую запись нельзя выдать за пакет без зависимостей."""
        with self.assertRaisesRegex(RepositoryError, "B"):
            self.graph({"A": ["B"]})

    def test_boundary_does_not_resolve_children(self):
        """За пределом глубины поиск зависимостей действительно прекращается."""
        graph = self.graph({"A": ["B"]}, depth=0)
        self.assertEqual(len(graph.nodes), 1)

    def test_filtered_missing_dependency(self):
        """Исключенная зависимость не требует наличия записи в каталоге."""
        graph = self.graph({"A": ["B"]}, excluded="B")
        self.assertEqual(len(graph.nodes), 1)

    def test_repeated_edges(self):
        """Повтор одной зависимости не дублирует узлы и связи."""
        graph = self.graph({"A": ["B", "B"], "B": []})
        self.assertEqual(len(graph.edges), 1)


if __name__ == "__main__":
    unittest.main()
