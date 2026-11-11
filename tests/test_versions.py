"""Независимые примеры порядка версий Debian и проверки ограничений."""

import unittest

from src.packages import Dependency
from src.versions import compare_versions, satisfies


class VersionTests(unittest.TestCase):
    """Сравнение чисел, эпох, ревизий и предварительных версий."""

    def test_order(self):
        """Числа сравниваются численно, тильда предшествует релизу."""
        pairs = [
            ("1.9", "1.10"), ("1.0~rc1", "1.0"),
            ("1.0~~", "1.0~"), ("1.0", "1.0+build"),
            ("1.0a", "1.0+"), ("1.0-2", "1.0-10"),
            ("2.0", "1:1.0"), ("1:9.0", "2:1.0"),
            ("1.0-1ubuntu2", "1.0-1ubuntu10"),
        ]
        for older, newer in pairs:
            with self.subTest(older=older, newer=newer):
                self.assertEqual(compare_versions(older, newer), -1)
                self.assertEqual(compare_versions(newer, older), 1)

    def test_equivalent_versions(self):
        """Отсутствующие эпоха и ревизия равны нулю, ведущие нули не важны."""
        pairs = [("1.0", "0:1.0"), ("1.0", "1.0-0"), ("1.01", "1.1")]
        for first, second in pairs:
            with self.subTest(first=first, second=second):
                self.assertEqual(compare_versions(first, second), 0)

    def test_constraint(self):
        """Каждый разрешенный оператор применяется к сравнению версий."""
        expected = {
            "<<": False, "<=": False, "=": False, ">=": True, ">>": True,
        }
        for relation, result in expected.items():
            dependency = Dependency("library", relation=relation, version="1.9")
            self.assertEqual(satisfies("1.10", dependency), result)
        self.assertTrue(satisfies("1.0", Dependency("library")))


if __name__ == "__main__":
    unittest.main()
