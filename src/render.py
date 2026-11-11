"""Локальный запуск PlantUML исключительно для рисования готового графа."""

import hashlib
import shutil
import subprocess
from pathlib import Path
from urllib.request import Request, urlopen


VERSION = "1.2026.10"
JAR_NAME = f"plantuml-{VERSION}.jar"
JAR_URL = (
    f"https://github.com/plantuml/plantuml/releases/download/v{VERSION}/"
    + JAR_NAME
)
# Контрольная сумма официального файла из метаданных релиза GitHub.
JAR_SHA256 = "e9bc9e6b2eb715e8c0c929f3dcb5fc1923be13f37599b09c293c66d354e88686"
MAX_JAR_BYTES = 64 * 1024 * 1024
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
ROOT = Path(__file__).resolve().parent.parent


class RenderError(ValueError):
    """Понятная ошибка подготовки или запуска визуализатора."""


def ensure_jar(filename=None):
    """Один раз скачать PlantUML либо использовать явно указанный JAR."""
    path = Path(filename) if filename else ROOT / "generated/tools" / JAR_NAME
    if filename:
        if not path.is_file():
            raise RenderError("Не найден указанный PlantUML JAR: " + str(path))
        return path.resolve()
    if path.is_file():
        if hashlib.sha256(path.read_bytes()).hexdigest() == JAR_SHA256:
            return path
    # Бинарный инструмент хранится только в папке, исключенной из Git.
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        request = Request(
            JAR_URL, headers={"User-Agent": "dependency-visualizer"}
        )
        with urlopen(request, timeout=60) as response:
            data = response.read(MAX_JAR_BYTES + 1)
    except OSError as error:
        raise RenderError(f"Не удалось скачать PlantUML: {error}") from error
    if len(data) > MAX_JAR_BYTES:
        raise RenderError("Размер файла PlantUML превышает допустимый.")
    if hashlib.sha256(data).hexdigest() != JAR_SHA256:
        raise RenderError("Не совпала официальная контрольная сумма PlantUML.")
    path.write_bytes(data)
    return path


def render_png(source, jar=None):
    """Передать готовый текст диаграммы Java и получить PNG в памяти."""
    java = shutil.which("java")
    if java is None:
        raise RenderError("Для изображения установите Java 17+.")
    jar = ensure_jar(jar)
    command = [
        java, "-Djava.awt.headless=true", "-jar", str(jar),
        "-charset", "UTF-8", "-tpng", "-pipe", "-failfast2",
    ]
    try:
        result = subprocess.run(
            command, input=source.encode("utf-8"), capture_output=True,
            timeout=120, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise RenderError(f"Не удалось запустить PlantUML: {error}") from error
    if result.returncode:
        details = result.stderr.decode("utf-8", errors="replace").strip()
        raise RenderError("Ошибка PlantUML: " + details)
    if not result.stdout.startswith(PNG_SIGNATURE):
        raise RenderError("PlantUML не вернул изображение PNG.")
    return result.stdout
