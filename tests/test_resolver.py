"""Выбор версий, альтернатив и поставщиков виртуальных пакетов."""

import unittest

from src.graph import build_graph
from src.packages import RepositoryError, find_package, parse_packages


def graph_from(text, depth=3, excluded=""):
    """Построить граф корневого app из небольшого индекса Ubuntu."""
    index = parse_packages(text)
    root = find_package(index, "app", "1.0")
    return build_graph(index, root, depth, excluded)


class ResolverTests(unittest.TestCase):
    """Проверить переход от объявленной зависимости к записи каталога."""

    def test_newest_satisfying_version(self):
        """Выбирается новейшая подходящая версия, а не строковый максимум."""
        graph = graph_from(
            "Package: app\nVersion: 1.0\nDepends: library (>= 1.9)\n\n"
            "Package: library\nVersion: 1.9\n\n"
            "Package: library\nVersion: 1.10\n\n"
            "Package: library\nVersion: 1.8\n"
        )
        self.assertIn(("library", "1.10"), graph.nodes)
        self.assertEqual(len(graph.nodes), 2)

    def test_exact_dependency_version(self):
        """Условие равенства не допускает выбора более новой версии."""
        graph = graph_from(
            "Package: app\nVersion: 1.0\nDepends: library (= 1.0)\n\n"
            "Package: library\nVersion: 1.0\n\n"
            "Package: library\nVersion: 2.0\n"
        )
        self.assertIn(("library", "1.0"), graph.nodes)
        self.assertNotIn(("library", "2.0"), graph.nodes)

    def test_unavailable_alternative(self):
        """Отсутствие одного варианта допустимо, когда другой есть в индексе."""
        graph = graph_from(
            "Package: app\nVersion: 1.0\nDepends: missing | library\n\n"
            "Package: library\nVersion: 1.0\n"
        )
        self.assertEqual(len(graph.edges), 1)
        self.assertEqual(graph.edges[0].group, "missing | library")

    def test_all_available_alternatives(self):
        """Возможные варианты сохраняются с подписью альтернативной группы."""
        graph = graph_from(
            "Package: app\nVersion: 1.0\nDepends: first | second\n\n"
            "Package: first\nVersion: 1.0\n\n"
            "Package: second\nVersion: 1.0\n"
        )
        self.assertEqual(len(graph.edges), 2)
        self.assertTrue(all(
            edge.group == "first | second" for edge in graph.edges
        ))

    def test_virtual_package(self):
        """Виртуальное имя продолжается через настоящий пакет-поставщик."""
        graph = graph_from(
            "Package: app\nVersion: 1.0\nDepends: virtual-api\n\n"
            "Package: provider\nVersion: 2.0\nProvides: virtual-api\n"
        )
        self.assertIn(("provider", "2.0"), graph.nodes)
        self.assertEqual(graph.edges[0].requirement, "virtual-api")

    def test_versioned_virtual_package(self):
        """Сравниваем объявленную версию услуги, а не версию поставщика."""
        graph = graph_from(
            "Package: app\nVersion: 1.0\nDepends: virtual-api (>= 3.0)\n\n"
            "Package: provider\nVersion: 1.0\nProvides: virtual-api (= 3.1)\n"
        )
        self.assertIn(("provider", "1.0"), graph.nodes)

    def test_virtual_without_required_version(self):
        """Без версии Provides нельзя подтвердить версионное требование."""
        with self.assertRaises(RepositoryError):
            graph_from(
                "Package: app\nVersion: 1.0\nDepends: virtual-api (>= 3)\n\n"
                "Package: provider\nVersion: 9.0\nProvides: virtual-api\n"
            )

    def test_filtered_provider(self):
        """Фильтр применяется и к настоящему имени виртуального поставщика."""
        graph = graph_from(
            "Package: app\nVersion: 1.0\nDepends: virtual-api\n\n"
            "Package: provider\nVersion: 1.0\nProvides: virtual-api\n",
            excluded="provider",
        )
        self.assertEqual(len(graph.nodes), 1)


if __name__ == "__main__":
    unittest.main()
