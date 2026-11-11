"""Обратный поиск должен учитывать весь каталог и точную выбранную версию."""

import io
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from src.graph import format_graph
from src.main import main
from src.packages import find_package, parse_packages
from src.reverse import build_reverse_graph
from tests.test_graph import make_index


class ReverseTests(unittest.TestCase):
    """Прямые и косвенные потребители, глубина, фильтр и циклы."""

    def graph(self, depth=3, excluded=""):
        """Создать две входящие ветки и одну исходящую зависимость B."""
        index = make_index({
            "A": ["B"], "B": ["D"], "C": ["B"], "E": ["A"], "D": [],
        })
        return build_reverse_graph(index, index[("B", "1.0")], depth, excluded)

    def test_other_branches_and_transitivity(self):
        """Находим C из другой ветки и косвенного потребителя E."""
        graph = self.graph()
        self.assertEqual([key[0] for key in graph.nodes], ["B", "A", "E", "C"])
        self.assertEqual(len(graph.edges), 3)
        self.assertNotIn(("D", "1.0"), graph.nodes)
        self.assertTrue(graph.reverse)

    def test_depth_limit(self):
        """На глубине 1 есть только непосредственные потребители A и C."""
        graph = self.graph(depth=1)
        self.assertEqual([key[0] for key in graph.nodes], ["B", "A", "C"])
        self.assertEqual(len(graph.edges), 2)

    def test_depth_zero(self):
        """Нулевая глубина оставляет только выбранный пакет."""
        self.assertEqual(list(self.graph(depth=0).nodes), [("B", "1.0")])

    def test_filter(self):
        """Исключение A отсекает также путь к E, но сохраняет C."""
        graph = self.graph(excluded="A")
        self.assertEqual([key[0] for key in graph.nodes], ["B", "C"])
        self.assertEqual(len(graph.edges), 1)

    def test_filtered_root(self):
        """Фильтр корня дает пустой граф и в обратном режиме."""
        self.assertFalse(self.graph(excluded="B").nodes)

    def test_cycle(self):
        """После разворота цикл сохраняется и обход завершается."""
        index = make_index({"A": ["B"], "B": ["C"], "C": ["A"]})
        graph = build_reverse_graph(index, index[("A", "1.0")], 5)
        self.assertEqual([key[0] for key in graph.nodes], ["A", "C", "B"])
        self.assertIn((("B", "1.0"), ("A", "1.0")), graph.cycle_edges)

    def test_no_dependents(self):
        """Пакет без потребителей остается единственным узлом."""
        index = make_index({"A": ["B"], "B": []})
        graph = build_reverse_graph(index, index[("A", "1.0")], 3)
        self.assertEqual(len(graph.nodes), 1)
        self.assertFalse(graph.edges)

    def test_missing_unrelated_dependency(self):
        """Неизвестная цель вне интересующей ветки не блокирует поиск."""
        index = make_index({"A": ["B"], "B": [], "C": ["MISSING"]})
        graph = build_reverse_graph(index, index[("B", "1.0")], 3)
        self.assertEqual([key[0] for key in graph.nodes], ["B", "A"])

    def test_older_target_version(self):
        """Наличие новой версии не скрывает потребителей выбранной старой."""
        index = parse_packages(
            "Package: library\nVersion: 1.0\n\n"
            "Package: library\nVersion: 2.0\n\n"
            "Package: app\nVersion: 1.0\nDepends: library (>= 1.0)\n\n"
            "Package: newer-app\nVersion: 1.0\nDepends: library (>= 2.0)\n"
        )
        root = find_package(index, "library", "1.0")
        graph = build_reverse_graph(index, root, 2)
        self.assertIn(("app", "1.0"), graph.nodes)
        self.assertNotIn(("newer-app", "1.0"), graph.nodes)

    def test_virtual_dependents(self):
        """Потребитель виртуального имени находится для реального поставщика."""
        index = parse_packages(
            "Package: provider\nVersion: 1.0\nProvides: virtual-api (= 3)\n\n"
            "Package: app\nVersion: 1.0\nDepends: virtual-api (>= 2)\n"
        )
        graph = build_reverse_graph(index, index[("provider", "1.0")], 3)
        self.assertIn(("app", "1.0"), graph.nodes)
        self.assertEqual(graph.edges[0].requirement, "virtual-api (>= 2)")

    def test_cli_reverse(self):
        """Флаг командной строки включает режим с пояснением стрелок."""
        filename = Path(__file__).resolve().parent.parent / "config-reverse.csv"
        output = io.StringIO()
        with redirect_stdout(output):
            result = main([str(filename), "--reverse"])
        self.assertEqual(result, 0)
        self.assertIn("Обратные зависимости B", output.getvalue())
        self.assertIn("Y зависит от X", output.getvalue())
        self.assertIn("B@1.0 -> A@1.0", output.getvalue())

    def test_direction_explanation(self):
        """В выводе явно указан обратный смысл направленных связей."""
        text = "\n".join(format_graph(self.graph()))
        self.assertIn("пакет Y зависит от X", text)


if __name__ == "__main__":
    unittest.main()
