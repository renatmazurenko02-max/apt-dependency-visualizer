"""Загрузка каталога, сжатие и ошибки сети проверяются без интернета."""

import bz2
import gzip
import io
import json
import lzma
import tempfile
import unittest
from pathlib import Path
from urllib.error import HTTPError, URLError
from unittest.mock import patch

from src.packages import RepositoryError, find_package
from src.source import _download, load_remote, load_test


TEXT = b"Package: app\nVersion: 1.0\nDepends: lib-one\n"
DIRECT = "https://example.org/Packages.xz"


class SourceTests(unittest.TestCase):
    """Проверить загрузку и обработку различных входных данных."""

    def test_all_compression_formats(self):
        """Поддерживаются обычный текст, xz, gzip и bzip2."""
        bodies = [
            TEXT, lzma.compress(TEXT), gzip.compress(TEXT), bz2.compress(TEXT)
        ]
        for body in bodies:
            with self.subTest(signature=body[:6]):
                with patch("src.source._download", return_value=body):
                    index = load_remote(DIRECT)
                package = find_package(index, "app", "1.0")
                self.assertEqual(package.dependencies[0][0].name, "lib-one")

    def test_index_directory_fallback(self):
        """Если xz отсутствует, пробуем gzip из той же папки."""
        missing = HTTPError(DIRECT, 404, "Not Found", {}, None)
        with patch("src.source._download") as download:
            download.side_effect = [missing, gzip.compress(TEXT)]
            index = load_remote("https://example.org/binary-amd64/")
        self.assertIn(("app", "1.0"), index)
        self.assertEqual(download.call_args.args[0],
                         "https://example.org/binary-amd64/Packages.gz")

    def test_http_and_network_errors(self):
        """404, ошибки сервера и недоступная сеть дают RepositoryError."""
        errors = [
            HTTPError(DIRECT, 404, "Not Found", {}, None),
            HTTPError(DIRECT, 503, "Unavailable", {}, None),
            URLError("offline"), TimeoutError("timeout"),
        ]
        for error in errors:
            with self.subTest(error=error):
                with patch("src.source._download", side_effect=error):
                    with self.assertRaises(RepositoryError):
                        load_remote(DIRECT)

    def test_corrupted_content(self):
        """Поврежденные архивы, кодировка и HTML не дают ложный результат."""
        bodies = [
            b"\xfd7zXZ\x00broken", b"\x1f\x8bbroken", b"BZhbroken",
            b"\xff\xfe", b"<html>Error</html>", b"",
        ]
        for body in bodies:
            with self.subTest(body=body):
                with patch("src.source._download", return_value=body):
                    with self.assertRaises(RepositoryError):
                        load_remote(DIRECT)

    def test_download_limit(self):
        """Загрузка ограничена; бесконечный ответ не читается целиком."""
        with patch("src.source.MAX_DOWNLOAD_BYTES", 4):
            with patch("src.source.urlopen", return_value=io.BytesIO(b"12345")):
                with self.assertRaises(RepositoryError):
                    _download(DIRECT)

    def test_decompressed_limit(self):
        """Ограничивается и размер распакованного текста."""
        body = gzip.compress(TEXT)
        with patch("src.source.MAX_TEXT_BYTES", 4):
            with patch("src.source._download", return_value=body):
                with self.assertRaises(RepositoryError):
                    load_remote(DIRECT)


class TestRepositoryTests(unittest.TestCase):
    """Учебный JSON позволяет пользоваться программой без сети."""

    def setUp(self):
        """Подготовить отдельный временный файл."""
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.filename = Path(self.temp.name) / "repository.json"

    def write_data(self, data):
        """Записать учебные данные для одного сценария."""
        self.filename.write_text(json.dumps(data), encoding="utf-8")

    def test_direct_dependencies(self):
        """Извлекаются только прямые связи, обход еще не выполняется."""
        self.write_data({
            "A": {"version": "1.0", "dependencies": ["B", "C"]},
            "B": {"version": "1.0", "dependencies": ["D"]},
        })
        package = find_package(load_test(self.filename), "A", "1.0")
        names = [group[0].name for group in package.dependencies]
        self.assertEqual(names, ["B", "C"])
        self.assertNotIn("D", names)

    def test_invalid_json_structure(self):
        """Неверные типы, имена и отсутствие полей явно отклоняются."""
        bad = [
            {}, [], {"a": {}}, {"A": []},
            {"A": {"version": 1, "dependencies": []}},
            {"A": {"version": "1", "dependencies": "B"}},
            {"A": {"version": "1", "dependencies": [1]}},
            {"A": {"version": "1", "dependencies": ["bad"]}},
        ]
        for data in bad:
            with self.subTest(data=data):
                self.write_data(data)
                with self.assertRaises(RepositoryError):
                    load_test(self.filename)

    def test_unreadable_json(self):
        """Отсутствующий, поврежденный и неверно закодированный JSON."""
        with self.assertRaises(RepositoryError):
            load_test(self.filename)
        for data in [b"{broken", b"\xff\xfe"]:
            self.filename.write_bytes(data)
            with self.assertRaises(RepositoryError):
                load_test(self.filename)


if __name__ == "__main__":
    unittest.main()
