"""Проверки дерева, PlantUML и файлов экспорта без сети и окон."""

import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from src.config import Config
from src.graph import build_graph
from src.packages import Package, parse_packages
from src.render import RenderError, render_png
from src.tree import format_tree
from src.visualize import export_graph, plantuml_source
from tests.test_graph import make_index


def example_graph(connections, depth=3):
    """Создать учебный граф для проверки независимого слоя отображения."""
    index = make_index(connections)
    return build_graph(index, index[("A", "1.0")], depth)


class TreeTests(unittest.TestCase):
    """ASCII-дерево не теряет короткие пути и не зацикливается."""

    def test_branch_connectors(self):
        """Положение веток остается понятным в обычном текстовом терминале."""
        graph = example_graph({"A": ["B", "C"], "B": ["D"], "C": [], "D": []})
        self.assertEqual(format_tree(graph, 3), [
            "A@1.0", "|-- B@1.0", "|   `-- D@1.0", "`-- C@1.0",
        ])

    def test_cycle_and_shared_node(self):
        """Цикл и общий узел помечаются разными пояснениями."""
        cycle = example_graph({"A": ["B"], "B": ["A"]})
        self.assertIn("[цикл]", "\n".join(format_tree(cycle, 3)))
        shared = example_graph({
            "A": ["B", "C"], "B": ["D"], "C": ["D"], "D": [],
        })
        self.assertIn("[повтор]", "\n".join(format_tree(shared, 3)))

    def test_shorter_path_in_tree(self):
        """Дерево раскрывает F после более короткого повторного пути к E."""
        graph = example_graph({
            "A": ["B", "C"], "B": ["D"], "D": ["E"],
            "C": ["E"], "E": ["F"], "F": [],
        })
        text = "\n".join(format_tree(graph, 3))
        self.assertIn("E@1.0 [предел глубины]", text)
        self.assertIn("F@1.0", text)

    def test_empty_graph(self):
        """Исключенный корень получает объяснение вместо ошибки вывода."""
        index = make_index({"A": []})
        graph = build_graph(index, index[("A", "1.0")], 3, "A")
        self.assertIn("исключен фильтром", format_tree(graph, 3)[0])


class ExportTests(unittest.TestCase):
    """Текст диаграммы и экспорт сохраняют данные графа."""

    def prepare(self):
        """Подготовить изолированные временные данные для одного теста.

        Каждый тест вызывает prepare явно; addCleanup удаляет временные файлы.
        """
        self.graph = example_graph({"A": ["B"], "B": []})
        self.config = Config("A", "unused.json", True, "1.0", True, 3, "")
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)

    def test_source_contains_all_nodes_and_edges(self):
        """Визуализатор получает ровно готовые узлы и направленные связи."""
        self.prepare()
        text = plantuml_source(self.graph)
        self.assertIn('rectangle "A\\n1.0" as n0', text)
        self.assertIn('rectangle "B\\n1.0" as n1', text)
        self.assertIn("n0 --> n1", text)
        self.assertTrue(text.endswith("@enduml\n"))

    def test_cycle_color(self):
        """Замыкание цикла отличается от обычной связи цветом и штрихами."""
        self.prepare()
        graph = example_graph({"A": ["B"], "B": ["A"]})
        self.assertIn("-[#C2413B,dashed]->", plantuml_source(graph))

    def test_virtual_provider_style(self):
        """Виртуальный поставщик визуально отличается от обычного требования."""
        self.prepare()
        index = parse_packages(
            "Package: app\nVersion: 1\nDepends: virtual-api\n\n"
            "Package: provider\nVersion: 1\nProvides: virtual-api\n"
        )
        graph = build_graph(index, index[("app", "1")], 2)
        self.assertIn("-[#7453A8,dashed]->", plantuml_source(graph))

    def test_text_export_without_java(self):
        """Офлайн-режим создает источник, данные и дерево без Java."""
        self.prepare()
        with patch("src.visualize.render_png") as render:
            files = export_graph(self.graph, self.config, self.folder, False)
        render.assert_not_called()
        self.assertTrue(files.source.is_file())
        self.assertIsNone(files.image)
        self.assertIn("B@1.0", files.tree.read_text(encoding="utf-8"))
        data = json.loads(files.data.read_text(encoding="utf-8"))
        self.assertEqual(len(data["nodes"]), 2)
        self.assertEqual(data["edges"][0]["target"], ["B", "1.0"])

    def test_disabled_tree(self):
        """Настройка false отключает создание дерева."""
        self.prepare()
        config = replace(self.config, ascii_tree=False)
        files = export_graph(self.graph, config, self.folder, False)
        self.assertIsNone(files.tree)
        self.assertFalse(list(self.folder.glob("*.tree.txt")))

    def test_safe_filename_for_epoch(self):
        """Двоеточие эпохи не превращается в недопустимое имя Windows."""
        self.prepare()
        root = Package("A", "1:1.0", ())
        graph = build_graph({("A", "1:1.0"): root}, root, 0)
        files = export_graph(graph, self.config, self.folder, False)
        self.assertEqual(files.source.name, "A-1_1.0.puml")

    def test_labels_cannot_break_source_lines(self):
        """Кавычки и переводы строк в метке остаются текстом метки."""
        self.prepare()
        root = Package('A"\n@enduml', "1.0", ())
        graph = build_graph({(root.name, root.version): root}, root, 0)
        text = plantuml_source(graph)
        self.assertEqual(text.splitlines().count("@enduml"), 1)
        self.assertIn("<U+0022>", text)


class RenderTests(unittest.TestCase):
    """Сбои Java не должны выдавать ошибочный файл за готовую картинку."""

    def test_missing_java(self):
        """До загрузки JAR объясняем отсутствие Java."""
        with patch("src.render.shutil.which", return_value=None):
            with self.assertRaisesRegex(RenderError, "Java"):
                render_png("@startuml\n@enduml")

    def test_wrong_renderer_output(self):
        """Даже успешный код процесса недостаточен без сигнатуры PNG."""
        with patch("src.render.shutil.which", return_value="java"):
            with patch("src.render.ensure_jar", return_value=Path("fake.jar")):
                with patch("src.render.subprocess.run") as run:
                    run.return_value.returncode = 0
                    run.return_value.stdout = b"not png"
                    with self.assertRaisesRegex(RenderError, "PNG"):
                        render_png("@startuml\n@enduml")


if __name__ == "__main__":
    unittest.main()
