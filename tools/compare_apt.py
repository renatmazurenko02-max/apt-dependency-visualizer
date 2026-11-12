"""Воспроизвести сравнение с apt-cache, отдельно от рабочего анализатора."""

import json
import shutil
import subprocess
from pathlib import Path

from .demo import ROOT, prepare


def native(work):
    """Выполнить штатную проверку во временном контейнере Ubuntu.

    Подключить только папку сравнения. Флаг --rm удаляет контейнер
    после завершения; устанавливаемое ПО остается внутри контейнера.
    """
    if shutil.which("docker") is None:
        raise RuntimeError("Для сравнения нужен запущенный Docker Desktop.")
    for filename in ("native_apt.py", "native_compare.sh"):
        shutil.copyfile(ROOT / "tools" / filename, work / filename)
    command = [
        "docker", "run", "--rm", "--mount",
        f"type=bind,source={work},target=/work", "ubuntu:24.04",
        "sh", "/work/native_compare.sh",
    ]
    subprocess.run(command, check=True, timeout=600)


def report(work):
    """Сравнить нормализованные результаты и сохранить расхождения."""
    request = json.loads((work / "request.json").read_text(encoding="utf-8"))
    rows = []
    differences = []
    for item in request["packages"]:
        ours = json.loads((work / "ours" / (item["stem"] + ".graph.json"))
                          .read_text(encoding="utf-8"))
        other = json.loads((work / "native" / (item["name"] + ".graph.json"))
                           .read_text(encoding="utf-8"))
        our_nodes = {node["name"] for node in ours["nodes"]}
        our_edges = {(edge["source"][0], edge["target"][0])
                     for edge in ours["edges"]}
        their_nodes = set(other["nodes"])
        their_edges = {tuple(edge) for edge in other["edges"]}
        same = our_nodes == their_nodes and our_edges == their_edges
        rows.append(f"| {item['name']} {item['version']} | {len(our_nodes)} / "
                    f"{len(their_nodes)} | {len(our_edges)} / "
                    f"{len(their_edges)} | {same} |")
        differences.append({
            "package": item["name"],
            "only_ours": sorted(our_edges - their_edges),
            "only_apt": sorted(their_edges - our_edges),
        })
    text = _report_text(work, request, rows, differences)
    output = ROOT / "docs/comparison.md"
    output.parent.mkdir(exist_ok=True)
    output.write_text(text, encoding="utf-8")
    print("Отчет: " + str(output))


def _report_text(work, request, rows, differences):
    """Объяснить границы проверки и различия представлений графа."""
    version = (work / "native/version.txt").read_text(encoding="utf-8").strip()
    return "\n".join([
        "# Сравнение со штатным apt-cache", "",
        "Воспроизведение: `python -m tools.compare_apt`.", "",
        "Среда: временный контейнер Ubuntu 24.04, " + version + ".",
        "Оба средства читают один индекс noble/main/binary-amd64.",
        "SHA-256 каталога: `" + request["catalog_sha256"] + "`.", "",
        "Наша программа выполняет DFS. Для независимой проверки вывод",
        "`apt-cache --important --recurse depends` обрабатывается через BFS.",
        "Глубина в обоих случаях 2; рекомендации и предложения исключены.", "",
        "| Пакет и версия | Узлы: наши / apt | Связи: наши / apt | Равны |",
        "| --- | --- | --- | --- |", *rows, "",
        "## Различия рисунков", "",
        "Наш рисунок создается PlantUML, штатный DOT получен `apt-cache dotty`",
        "и отрисован Graphviz. Для ограничения DOT используются имена узлов,",
        "которые независимый BFS достиг до предельного уровня.",
        "Штатный DOT также показывает конфликты и виртуальные имена отдельно;",
        "наш граф показывает обязательные зависимости и реальные поставщики.",
        "Поэтому форма, цвета, число вспомогательных узлов и размещение",
        "блоков могут различаться при совпадающих обязательных связях.", "",
        "Сравнение нормализовано по именам, версии в этом индексе однозначны.",
        "Версии и условия дополнительно сохраняются в нашем PNG и PlantUML.",
        "Сырые DOT, PNG, вывод depends и JSON лежат в `generated/comparison/`.",
        "Бинарные файлы исключены из Git; команды заново создают примеры.", "",
        "## Фактические расхождения связей", "", "```json",
        json.dumps(differences, ensure_ascii=False, indent=2), "```", "",
        "Источник поведения штатных средств:",
        "[Описание apt-cache]("
        "https://manpages.ubuntu.com/manpages/noble/man8/apt-cache.8.html)", "",
    ])


if __name__ == "__main__":
    folder = prepare()
    native(folder)
    report(folder)
