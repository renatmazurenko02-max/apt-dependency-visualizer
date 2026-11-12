"""Экспорт готового графа в PlantUML, PNG и данные для проверки."""

import json
import os
import re
import textwrap
import webbrowser
from dataclasses import asdict, dataclass
from pathlib import Path

from .render import render_png
from .tree import format_tree


@dataclass(frozen=True)
class Artifacts:
    """Пути к файлам одного запуска; image и tree могут отсутствовать."""

    source: Path
    image: Path | None
    data: Path
    tree: Path | None


def _escape(text):
    """Сохранить текст метки, не позволяя ему менять команды PlantUML."""
    return (
        text.replace("\\", "<U+005C>").replace('"', "<U+0022>")
        .replace("\r", "").replace("\n", r"\n")
    )


def _label(edge, graph):
    """Вернуть подпись условия версии или группы альтернатив.

    Для совпадающего простого имени подпись не нужна. Длинный текст
    разбить на строки шириной 36 символов для читаемой диаграммы.
    """
    name = edge.source[0] if graph.reverse else edge.target[0]
    text = edge.group if "|" in edge.group else edge.requirement
    if text == name:
        return ""
    return "\n".join(textwrap.wrap(text, width=36))


def _alternative(edge, graph):
    """Отметить выбор альтернативы или поставщика виртуального имени."""
    actual = edge.source[0] if graph.reverse else edge.target[0]
    requested = edge.requirement.split()[0].split(":")[0]
    return "|" in edge.group or requested != actual


def _edge_source(edge, graph, names):
    """Описать одну стрелку с ее цветом, направлением и подписью."""
    cycle = (edge.source, edge.target) in graph.cycle_edges
    arrow = "-[#C2413B,dashed]->" if cycle else "-->"
    if _alternative(edge, graph) and not cycle:
        arrow = "-[#7453A8,dashed]->"
    text = f"{names[edge.source]} {arrow} {names[edge.target]}"
    label = _label(edge, graph)
    if label:
        text += " : " + _escape(label)
    return text


def plantuml_source(graph):
    """Описать узлы и связи на PlantUML без анализа зависимостей заново."""
    direction = "Reverse dependencies" if graph.reverse else "Dependencies"
    lines = [
        "@startuml", "!pragma layout smetana", "left to right direction",
        "skinparam backgroundColor white", "skinparam shadowing false",
        "skinparam defaultFontName SansSerif", "skinparam roundcorner 10",
        f"title {direction}: {_escape('@'.join(graph.root))}",
    ]
    names = {key: f"n{number}" for number, key in enumerate(graph.nodes)}
    for key in graph.nodes:
        label = _escape(key[0] + "\n" + key[1])
        color = "#DBEAFE" if key == graph.root else "#F4F7FB"
        lines.append(f'rectangle "{label}" as {names[key]} {color}')
    if not graph.nodes:
        lines.append('rectangle "Root excluded by filter" as empty #F4F7FB')
    for edge in graph.edges:
        lines.append(_edge_source(edge, graph, names))
    if graph.reverse:
        lines.append("caption Arrow X -> Y: package Y requires X")
    lines.append("@enduml")
    return "\n".join(lines) + "\n"


def graph_data(graph):
    """Сохранить узлы и исходные условия для воспроизводимого сравнения."""
    return {
        "root": graph.root, "reverse": graph.reverse,
        "nodes": [
            {"name": key[0], "version": key[1], "depth": graph.depths[key]}
            for key in graph.nodes
        ],
        "edges": [asdict(edge) for edge in graph.edges],
    }


def export_graph(graph, config, output, image=True, jar=None):
    """Сохранить граф в файлы и вернуть пути в объекте Artifacts.

    Всегда создать PlantUML и JSON, по настройкам создать дерево и PNG.
    Заменить недопустимые символы имени файла, включая двоеточие эпохи,
    чтобы результат сохранялся и в Windows.
    """
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    stem = re.sub(r"[^A-Za-z0-9_.-]", "_", "-".join(graph.root))
    if graph.reverse:
        stem += "-reverse"
    source = output / (stem + ".puml")
    data = output / (stem + ".graph.json")
    tree = output / (stem + ".tree.txt") if config.ascii_tree else None
    text = plantuml_source(graph)
    source.write_text(text, encoding="utf-8")
    data.write_text(json.dumps(graph_data(graph), indent=2), encoding="utf-8")
    if tree:
        tree.write_text(
            "\n".join(format_tree(graph, config.max_depth)) + "\n",
            encoding="utf-8",
        )
    png = output / (stem + ".png") if image else None
    if png:
        png.write_bytes(render_png(text, jar))
    return Artifacts(source, png, data, tree)


def show_image(filename):
    """Открыть PNG стандартной программой после явного запуска пользователем."""
    path = Path(filename).resolve()
    if os.name == "nt":
        os.startfile(str(path))
    else:
        webbrowser.open(path.as_uri())
