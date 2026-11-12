"""Независимое сравнение: apt-cache и BFS; запускается внутри Ubuntu."""

import json
import os
import re
import subprocess
import sys
from collections import deque
from pathlib import Path


def apt(work, *arguments):
    """Использовать общий каталог с пустым статусом установленных пакетов."""
    options = [
        "apt-cache", "-o", f"Dir::Etc::sourcelist={work}/sources.list",
        "-o", "Dir::Etc::sourceparts=-",
        "-o", f"Dir::State::lists={work}/lists",
        "-o", f"Dir::State::status={work}/status",
        "-o", "Dir::Cache::pkgcache=", "-o", "Dir::Cache::srcpkgcache=",
    ]
    return subprocess.check_output(
        options + list(arguments), text=True, encoding="utf-8",
        env=dict(os.environ, LC_ALL="C"), timeout=60,
    )


def _native_dependency(adjacent, parent, line, virtual):
    """Добавить одну обычную зависимость или поставщика виртуального имени."""
    match = re.match(r"\s*\|?(?:Pre)?Depends:\s*(\S+)", line)
    if match:
        name = match.group(1)
        virtual = name.startswith("<")
        if not virtual:
            adjacent[parent].add(name.split(":")[0])
    elif virtual and line.startswith("    "):
        name = line.strip().split(":")[0]
        if name and not name.startswith("<"):
            adjacent[parent].add(name)
    return virtual


def parse_native(text):
    """Прочитать вывод depends с поставщиками виртуальных имен."""
    adjacent = {}
    parent = None
    virtual = False
    for line in text.splitlines():
        if line and not line[0].isspace():
            parent = None if line.startswith("<") else line.strip()
            virtual = False
            if parent:
                adjacent.setdefault(parent, set())
        elif parent:
            virtual = _native_dependency(adjacent, parent, line, virtual)
    return adjacent


def cut_graph(adjacent, root, max_depth):
    """Независимый BFS ограничивает результат тем же числом переходов."""
    depths = {root: 0}
    edges = set()
    queue = deque([root])
    while queue:
        name = queue.popleft()
        if depths[name] >= max_depth:
            continue
        for target in sorted(adjacent.get(name, ())):
            edges.add((name, target))
            if target not in depths:
                depths[target] = depths[name] + 1
                queue.append(target)
    return depths, edges


def collect(work):
    """Сохранить штатные DOT/PNG и независимые списки узлов и связей.

    Сначала проверить наличие запрошенной версии через apt-cache show.
    Сохранить вывод depends и ограничить его глубину независимым BFS.
    """
    work = Path(work)
    output = work / "native"
    output.mkdir(exist_ok=True)
    (output / "version.txt").write_text(
        apt(work, "--version"), encoding="utf-8"
    )
    requests = json.loads((work / "request.json").read_text(encoding="utf-8"))
    for item in requests["packages"]:
        name = item["name"]
        apt(work, "show", name + "=" + item["version"])
        text = apt(work, "--important", "--recurse", "depends", name)
        (output / (name + ".depends.txt")).write_text(text, encoding="utf-8")
        depths, edges = cut_graph(parse_native(text), name, item["max_depth"])
        expanded = sorted(
            key for key in depths if depths[key] < item["max_depth"]
        )
        dot = apt(work, "-o", "APT::Cache::GivenOnly=true", "dotty", *expanded)
        dotfile = output / (name + ".dot")
        dotfile.write_text(dot, encoding="utf-8")
        subprocess.run(["dot", "-Tpng", str(dotfile), "-o",
                        str(output / (name + ".png"))], check=True, timeout=60)
        (output / (name + ".graph.json")).write_text(json.dumps({
            "nodes": depths, "edges": sorted(edges),
        }, indent=2), encoding="utf-8")


if __name__ == "__main__":
    collect(sys.argv[1] if len(sys.argv) > 1 else "/work")
