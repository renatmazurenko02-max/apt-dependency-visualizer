"""Проверки собственного парсера каталога и поиска точной версии."""

import unittest

from src.packages import (
    RepositoryError, find_package, format_dependency, parse_dependencies,
    parse_packages,
)


CATALOG = """Package: app
Version: 1.0
Pre-Depends: base (>= 1:2.0)
Depends: lib-one (>= 2.0),
 lib-two:any | lib-three:native, tool
Recommends: optional
Description: Test
 continuation

Package: app
Version: 2.0
Depends: newer

Package: tool
Version: 1.0
"""


class PackageTests(unittest.TestCase):
    """Данные разных версий и альтернативы нельзя смешивать или терять."""

    def test_exact_version_and_multiline_dependencies(self):
        """Для 1.0 читаются ее поля, включая продолжение и Pre-Depends."""
        package = find_package(parse_packages(CATALOG), "app", "1.0")
        actual = [format_dependency(group) for group in package.dependencies]
        self.assertEqual(actual, [
            "base (>= 1:2.0)", "lib-one (>= 2.0)",
            "lib-two:any | lib-three:native", "tool",
        ])
        self.assertNotIn("optional", actual)
        self.assertEqual(package.dependencies[1][0].version, "2.0")

    def test_another_version(self):
        """Версия 2.0 имеет собственные зависимости."""
        package = find_package(parse_packages(CATALOG), "app", "2.0")
        self.assertEqual(format_dependency(package.dependencies[0]), "newer")

    def test_missing_package_and_version(self):
        """Отсутствие пакета отличается от отсутствия конкретной версии."""
        index = parse_packages(CATALOG)
        with self.assertRaisesRegex(RepositoryError, "Пакет absent не найден"):
            find_package(index, "absent", "1.0")
        with self.assertRaisesRegex(RepositoryError, "Доступны: 1.0, 2.0"):
            find_package(index, "app", "3.0")

    def test_no_dependencies(self):
        """Отсутствующее поле Depends означает пустой список зависимостей."""
        package = find_package(parse_packages(CATALOG), "tool", "1.0")
        self.assertEqual(package.dependencies, ())
        self.assertEqual(parse_dependencies("  "), ())

    def test_all_version_operators(self):
        """Операторы Debian сохраняются в модели без подмены смысла."""
        for operator in ["<<", "<=", "=", ">=", ">>"]:
            with self.subTest(operator=operator):
                text = f"tool ({operator} 1.0~rc1-2)"
                groups = parse_dependencies(text)
                self.assertEqual(format_dependency(groups[0]), text)

    def test_invalid_dependency(self):
        """Неверные записи нельзя молча превратить в пустые зависимости."""
        for text in ["tool,", "| tool", "tool |", "tool (=> 1)", "???"]:
            with self.subTest(text=text):
                with self.assertRaises(RepositoryError):
                    parse_dependencies(text)

    def test_invalid_records(self):
        """Пустые, неполные и неоднозначные записи отклоняются."""
        invalid = [
            "", "Package: app\n", "Version: 1.0\n", "not a field",
            " continuation", "Package: app\nPackage: other\nVersion: 1.0",
            "Package: app\nVersion: 1\n\nPackage: app\nVersion: 1",
        ]
        for text in invalid:
            with self.subTest(text=text):
                with self.assertRaises(RepositoryError):
                    parse_packages(text)

    def test_last_record_without_blank_line(self):
        """Последняя запись читается и без завершающей пустой строки."""
        index = parse_packages("Package: app\r\nVersion: 1.0")
        self.assertEqual(find_package(index, "app", "1.0").name, "app")


if __name__ == "__main__":
    unittest.main()
