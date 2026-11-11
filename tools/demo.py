"""Создать три настоящих примера, используя только наш анализатор."""

import hashlib
import json
from pathlib import Path

from src.config import load_config
from src.graph import build_graph
from src.packages import find_package, parse_packages
from src.source import _decode, _download
from src.visualize import export_graph


ROOT = Path(__file__).resolve().parent.parent
WORK = ROOT / "generated/comparison"
INDEX_NAME = "archive.ubuntu.com_ubuntu_dists_noble_main_binary-amd64_Packages"
CONFIGS = ("config-visual-curl.csv", "config-gzip.csv", "config-bash.csv")


def catalog(work):
    """Сохранить один каталог для нашей программы и независимого apt-cache."""
    config = load_config(ROOT / CONFIGS[0])
    filename = work / "lists" / INDEX_NAME
    filename.parent.mkdir(parents=True, exist_ok=True)
    if not filename.is_file():
        filename.write_text(_decode(_download(config.repository)),
                            encoding="utf-8")
    text = filename.read_text(encoding="utf-8")
    (work / "sources.list").write_text(
        "deb [trusted=yes] https://archive.ubuntu.com/ubuntu noble main\n",
        encoding="utf-8",
    )
    (work / "status").write_text("", encoding="utf-8")
    checksum = hashlib.sha256(filename.read_bytes()).hexdigest()
    return parse_packages(text), checksum


def prepare(work=WORK):
    """Построить и нарисовать графы curl, gzip и bash на глубине 2."""
    work = Path(work).resolve()
    index, checksum = catalog(work)
    requests = []
    for filename in CONFIGS:
        config = load_config(ROOT / filename)
        package = find_package(
            index, config.package_name, config.package_version
        )
        graph = build_graph(index, package, config.max_depth)
        files = export_graph(graph, config, work / "ours")
        requests.append({
            "name": package.name, "version": package.version,
            "max_depth": config.max_depth, "stem": files.source.stem,
        })
        print(f"{package.name}: {len(graph.nodes)} узлов, "
              f"{len(graph.edges)} связей", flush=True)
    (work / "request.json").write_text(json.dumps({
        "catalog_sha256": checksum, "packages": requests,
    }, indent=2), encoding="utf-8")
    return work


if __name__ == "__main__":
    prepare()
