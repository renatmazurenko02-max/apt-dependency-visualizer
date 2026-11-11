"""Проверка независимого чтения вывода штатного инструмента apt-cache."""

import unittest

from tools.native_apt import cut_graph, parse_native


class NativeTests(unittest.TestCase):
    """Проверка вывода apt независима от нашего DFS и парсера Packages."""

    def test_virtual_and_alternative(self):
        """Реальное имя поставщика берется из строки под виртуальным именем."""
        text = (
            "app\n  Depends: <virtual-api>\n    provider\n"
            " |Depends: first\n  Depends: second\n"
            "provider\n  PreDepends: base\n<virtual-api>\n"
        )
        adjacent = parse_native(text)
        self.assertEqual(adjacent["app"], {"provider", "first", "second"})
        self.assertEqual(adjacent["provider"], {"base"})

    def test_bfs_depth(self):
        """Независимый обход проверяет уровень и не повторяется на цикле."""
        adjacent = {"A": {"B", "C"}, "B": {"D"}, "C": {"D"}, "D": {"A"}}
        depths, edges = cut_graph(adjacent, "A", 1)
        self.assertEqual(depths, {"A": 0, "B": 1, "C": 1})
        self.assertEqual(edges, {("A", "B"), ("A", "C")})
        depths, edges = cut_graph(adjacent, "A", 4)
        self.assertEqual(depths["D"], 2)
        self.assertIn(("D", "A"), edges)


if __name__ == "__main__":
    unittest.main()
