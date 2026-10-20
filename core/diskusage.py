"""Speicherplatz-Analyse: Ordnerbaum einlesen und als Treemap-Rechtecke anordnen (ohne UI, testbar)."""

import os
import threading
from dataclasses import dataclass, field

SMALL_FILES_NAME = "[kleine Dateien]"


@dataclass(eq=False)
class Node:
    name: str
    path: str
    size: int = 0
    is_dir: bool = False
    is_aggregate: bool = False  # Sammelknoten für viele kleine Dateien
    file_count: int = 0
    children: list["Node"] = field(default_factory=list)
    parent: "Node | None" = None


class ScanCancelled(Exception):
    pass


def format_size(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{int(n)} B" if unit == "B" else f"{n:.1f} {unit}".replace(".", ",")
        n /= 1024
    return ""


def _is_link(entry: os.DirEntry) -> bool:
    try:
        if entry.is_symlink():
            return True
        is_junction = getattr(entry, "is_junction", None)
        return bool(is_junction and is_junction())
    except OSError:
        return True


def scan(root: str, cancel: threading.Event | None = None, progress=None,
         min_file_size: int = 1 << 20) -> Node:
    """Liest `root` rekursiv ein. Symlinks/Junctions werden übersprungen.

    Dateien unter `min_file_size` werden pro Ordner zu einem Sammelknoten zusammengefasst,
    damit der Baum auch bei Millionen Dateien klein bleibt.
    `progress(file_count, total_bytes)` wird gelegentlich aufgerufen.
    """
    root = os.path.abspath(root)
    state = {"files": 0, "bytes": 0}

    def walk(path: str, name: str, parent: Node | None) -> Node:
        node = Node(name=name, path=path, is_dir=True, parent=parent)
        small_size = small_count = 0
        try:
            entries = list(os.scandir(path))
        except OSError:
            return node
        for entry in entries:
            if cancel is not None and cancel.is_set():
                raise ScanCancelled
            if _is_link(entry):
                continue
            try:
                if entry.is_dir(follow_symlinks=False):
                    child = walk(entry.path, entry.name, node)
                    node.children.append(child)
                    node.size += child.size
                    node.file_count += child.file_count
                elif entry.is_file(follow_symlinks=False):
                    size = entry.stat(follow_symlinks=False).st_size
                    node.size += size
                    node.file_count += 1
                    state["files"] += 1
                    state["bytes"] += size
                    if size >= min_file_size:
                        node.children.append(Node(entry.name, entry.path, size, parent=node, file_count=1))
                    else:
                        small_size += size
                        small_count += 1
                    if progress is not None and state["files"] % 2000 == 0:
                        progress(state["files"], state["bytes"])
            except OSError:
                continue
        if small_count:
            node.children.append(Node(SMALL_FILES_NAME, path, small_size, is_aggregate=True,
                                      file_count=small_count, parent=node))
        node.children.sort(key=lambda n: n.size, reverse=True)
        return node

    tree = walk(root, root, None)
    if progress is not None:
        progress(state["files"], state["bytes"])
    return tree


def _worst(row: list[float], side: float) -> float:
    s = sum(row)
    return max(side * side * max(row) / (s * s), s * s / (side * side * min(row)))


def squarify(values: list[float], x: float, y: float, w: float, h: float) -> list[tuple[float, float, float, float]]:
    """Squarified Treemap. `values` absteigend sortiert, > 0. Liefert (x, y, w, h) je Wert in gleicher Reihenfolge."""
    total = sum(values)
    if not values or w <= 0 or h <= 0 or total <= 0:
        return []
    scale = w * h / total
    areas = [v * scale for v in values]
    rects: list[tuple[float, float, float, float]] = []
    i = 0
    while i < len(areas):
        side = min(w, h)
        row = [areas[i]]
        j = i + 1
        while j < len(areas) and _worst(row + [areas[j]], side) <= _worst(row, side):
            row.append(areas[j])
            j += 1
        s = sum(row)
        if w >= h:  # Spalte links, Breite s/h
            col_w = s / h
            cy = y
            for a in row:
                rh = a / col_w
                rects.append((x, cy, col_w, rh))
                cy += rh
            x += col_w
            w -= col_w
        else:  # Zeile oben, Höhe s/w
            row_h = s / w
            cx = x
            for a in row:
                cw = a / row_h
                rects.append((cx, y, cw, row_h))
                cx += cw
            y += row_h
            h -= row_h
        i = j
    return rects
