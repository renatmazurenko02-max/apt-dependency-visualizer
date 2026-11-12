"""Показ этапов должен выполнять код и требовать новую загрузку из сети."""

import io
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from src.config import load_config
from tools.defense import (
    CONFIGS, INDEX_NAME, ROOT, Presentation, Stopped, arguments,
    invalid_examples, main,
)


class DefenseTests(unittest.TestCase):
    """Проверить реальные ошибки настроек, сетевую зависимость и протокол."""

    def prepare(self):
        """Подготовить изолированные временные данные для одного теста.

        Каждый тест вызывает prepare явно; addCleanup удаляет временные файлы.
        """
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.argv = [
            "--output", str(self.folder), "--no-pause", "--no-open",
            "--no-image", "--no-tests",
        ]

    def test_errors_cover_all_settings_without_modification(self):
        """Каждая ошибка относится к своему параметру, рабочий CSV сохранен."""
        self.prepare()
        filename = ROOT / "config.csv"
        before = filename.read_bytes()
        examples = list(invalid_examples(load_config(filename)))
        self.assertEqual(len(examples), 7)
        for key, value, message in examples:
            self.assertIn(key, message)
        self.assertEqual(filename.read_bytes(), before)

    def test_fresh_download_even_with_cache(self):
        """Существующий каталог не отменяет сетевой запрос второго этапа."""
        self.prepare()
        filename = self.folder / "lists" / INDEX_NAME
        filename.parent.mkdir()
        filename.write_text("OLD", encoding="utf-8")
        config = load_config(ROOT / CONFIGS[0])
        data = (f"Package: {config.package_name}\n"
                f"Version: {config.package_version}\n").encode()
        presentation = Presentation(arguments(self.argv))
        with patch("tools.defense.WORK", self.folder):
            with patch(
                "tools.defense._download", return_value=data
            ) as download:
                with redirect_stdout(io.StringIO()):
                    presentation.stage2()
        download.assert_called_once_with(config.repository)
        self.assertEqual(len(presentation.index), 1)
        self.assertNotIn("OLD", filename.read_text(encoding="utf-8"))

    def test_network_error_does_not_use_cache(self):
        """Сбой сети останавливает показ без подмены данных старой копией."""
        self.prepare()
        filename = self.folder / "lists" / INDEX_NAME
        filename.parent.mkdir()
        filename.write_text("OLD", encoding="utf-8")
        presentation = Presentation(arguments(self.argv))
        with patch("tools.defense.WORK", self.folder):
            with patch(
                "tools.defense._download", side_effect=OSError("offline")
            ):
                with redirect_stdout(io.StringIO()):
                    with self.assertRaises(OSError):
                        presentation.stage2()
        self.assertIsNone(presentation.index)
        self.assertEqual(filename.read_text(encoding="utf-8"), "OLD")

    def test_pause_allows_quit(self):
        """На паузе можно закончить показ без технической ошибки."""
        self.prepare()
        args = arguments(["--output", str(self.folder)])
        with patch("builtins.input", return_value="q"):
            with redirect_stdout(io.StringIO()):
                with self.assertRaises(Stopped):
                    Presentation(args).pause()

    def test_transcript(self):
        """Протокол содержит тот же фактический вывод, что и терминал."""
        self.prepare()
        output = io.StringIO()
        with patch(
            "tools.defense.Presentation.run", side_effect=lambda: print("OK")
        ):
            with redirect_stdout(output):
                code = main(self.argv)
        self.assertEqual(code, 0)
        text = (self.folder / "transcript.txt").read_text(encoding="utf-8")
        self.assertIn("OK", text)
        self.assertIn("OK", output.getvalue())

    def test_errors_are_recorded(self):
        """Ошибка сети отражается в коде завершения и в протоколе."""
        self.prepare()
        with patch(
            "tools.defense.Presentation.run", side_effect=OSError("offline")
        ):
            with redirect_stderr(io.StringIO()):
                code = main(self.argv)
        self.assertEqual(code, 1)
        text = (self.folder / "transcript.txt").read_text(encoding="utf-8")
        self.assertIn("offline", text)


if __name__ == "__main__":
    unittest.main()
