"""Проверки всех параметров и ошибок CSV без сетевых запросов."""

import csv
import io
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from src.config import ConfigError, FIELDS, load_config
from src.main import main


class ConfigTests(unittest.TestCase):
    """Изолированные сценарии чтения пользовательских настроек."""

    def setUp(self):
        """Создать отдельную папку и минимальные входные файлы."""
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = self.root / "config.csv"
        (self.root / "graph.json").write_text(
            '{"A": {"version": "1.0", "dependencies": []}}', encoding="utf-8"
        )
        self.values = {
            "package_name": "A",
            "repository": "graph.json",
            "test_mode": "true",
            "package_version": "1.0",
            "ascii_tree": "false",
            "max_depth": "3",
            "filter_substring": "",
        }

    def write_config(self, **changes):
        """Записать CSV с нужными для конкретного теста изменениями."""
        values = self.values | changes
        with self.path.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow(["parameter", "value"])
            writer.writerows(values.items())

    def test_valid_local_config(self):
        """Относительный путь разрешается от CSV, не от рабочей папки."""
        self.write_config()
        config = load_config(self.path)
        self.assertEqual(config.package_name, "A")
        self.assertTrue(config.test_mode)
        self.assertFalse(config.ascii_tree)
        self.assertEqual(config.max_depth, 3)
        self.assertEqual(config.filter_substring, "")

    def test_valid_remote_config(self):
        """В сетевом режиме проверяется адрес, сеть пока не используется."""
        self.write_config(
            package_name="curl", test_mode="false",
            repository="https://example.org/ubuntu/", max_depth="0",
            package_version="1:8.5.0-2ubuntu10.6", filter_substring="lib",
        )
        config = load_config(self.path)
        self.assertFalse(config.test_mode)
        self.assertEqual(config.max_depth, 0)
        self.assertEqual(config.filter_substring, "lib")

    def test_invalid_parameters(self):
        """Каждый из семи параметров имеет сценарий ошибочного ввода."""
        cases = [
            ("package_name", "a", "package_name"),
            ("repository", "missing.json", "repository"),
            ("test_mode", "yes", "test_mode"),
            ("package_version", "", "package_version"),
            ("package_version", "abc", "package_version"),
            ("ascii_tree", "1", "ascii_tree"),
            ("max_depth", "-1", "max_depth"),
            ("max_depth", "1.5", "max_depth"),
            ("max_depth", "", "max_depth"),
            ("filter_substring", "a\nb", "filter_substring"),
        ]
        for key, value, message in cases:
            with self.subTest(parameter=key, value=value):
                self.write_config(**{key: value})
                with self.assertRaisesRegex(ConfigError, message):
                    load_config(self.path)

    def test_invalid_remote_urls(self):
        """Ошибки схемы, хоста, порта и пробелов выявляются до запроса."""
        urls = [
            "", "ftp://example.org", "https:///ubuntu", "not-a-url",
            "https://example.org:bad", "https://example.org:70000",
            "https://example.org/a b", "https://[invalid",
        ]
        for url in urls:
            with self.subTest(url=url):
                self.write_config(
                    package_name="curl", test_mode="false", repository=url
                )
                with self.assertRaisesRegex(ConfigError, "repository"):
                    load_config(self.path)

    def test_invalid_ubuntu_package_name(self):
        """В обычном режиме прописные буквы в имени не допускаются."""
        self.write_config(test_mode="false", package_name="Curl")
        with self.assertRaisesRegex(ConfigError, "package_name"):
            load_config(self.path)

    def test_all_fields_required(self):
        """Даже пустой фильтр должен присутствовать отдельной строкой."""
        for key in FIELDS:
            with self.subTest(missing=key):
                self.write_config()
                lines = self.path.read_text(encoding="utf-8").splitlines()
                text = "\n".join(
                    line for line in lines if not line.startswith(key + ",")
                )
                self.path.write_text(text, encoding="utf-8")
                with self.assertRaisesRegex(ConfigError, key):
                    load_config(self.path)

    def test_duplicate_unknown_and_extra_columns(self):
        """Неоднозначные или неизвестные строки нельзя молча пропустить."""
        for extra in ["max_depth,2", "unknown,1", "max_depth,2,3"]:
            with self.subTest(extra=extra):
                self.write_config()
                with self.path.open("a", encoding="utf-8") as stream:
                    stream.write(extra + "\n")
                with self.assertRaises(ConfigError):
                    load_config(self.path)

    def test_bad_csv_and_encoding(self):
        """Поврежденный CSV, неверный заголовок и кодировка дают ошибку."""
        for text in ["", "key,value\n", 'parameter,value\n"unclosed']:
            with self.subTest(text=text):
                self.path.write_text(text, encoding="utf-8")
                with self.assertRaises(ConfigError):
                    load_config(self.path)
        self.path.write_bytes(b"\xff\xfe\x00")
        with self.assertRaises(ConfigError):
            load_config(self.path)

    def test_utf8_bom(self):
        """Допускается UTF-8 с BOM, который добавляют некоторые редакторы."""
        self.write_config()
        text = self.path.read_text(encoding="utf-8")
        self.path.write_text(text, encoding="utf-8-sig")
        self.assertEqual(load_config(self.path).package_name, "A")

    def test_missing_config(self):
        """Отсутствующий файл конфигурации дает управляемую ошибку."""
        with self.assertRaises(ConfigError):
            load_config(self.path)

    def test_cli_success(self):
        """Пакет без зависимостей образует граф из одного узла."""
        self.write_config()
        output = io.StringIO()
        with redirect_stdout(output):
            result = main([
                str(self.path), "--no-image", "--output", str(self.root / "out")
            ])
        self.assertEqual(result, 0)
        self.assertIn("Граф зависимостей A (версия 1.0):", output.getvalue())
        self.assertIn("Узлов: 1; связей: 0", output.getvalue())
        self.assertNotIn("ASCII-дерево:", output.getvalue())

    def test_cli_failure(self):
        """Ошибка выводится в stderr, возвращается ненулевой код."""
        self.write_config(max_depth="-1")
        output, errors = io.StringIO(), io.StringIO()
        with redirect_stdout(output), redirect_stderr(errors):
            result = main([str(self.path)])
        self.assertEqual(result, 1)
        self.assertEqual(output.getvalue(), "")
        self.assertIn("max_depth", errors.getvalue())


if __name__ == "__main__":
    unittest.main()
