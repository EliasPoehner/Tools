"""Speicherplatz-Analyse: Ordnerbaum einlesen und als Treemap-Rechtecke anordnen (ohne UI, testbar)."""

import os
import queue
import threading
from dataclasses import dataclass, field

SMALL_FILES_NAME = "[kleine Dateien]"

# Windows: Datei liegt nur in der Cloud (OneDrive „Bei Bedarf“ o. Ä.) und belegt lokal keinen Platz.
FILE_ATTRIBUTE_OFFLINE = 0x1000
FILE_ATTRIBUTE_RECALL_ON_DATA_ACCESS = 0x400000
_CLOUD_ONLY = FILE_ATTRIBUTE_OFFLINE | FILE_ATTRIBUTE_RECALL_ON_DATA_ACCESS


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


def format_count(n: int) -> str:
    """Ganzzahl mit deutschem Tausenderpunkt: 12345 -> „12.345“."""
    return f"{n:,}".replace(",", ".")


def _is_junction(entry: os.DirEntry) -> bool:
    try:
        return entry.is_junction()  # Python 3.12+; Junctions zählen nicht als Symlink
    except (AttributeError, OSError):
        return False


DEFAULT_WORKERS = min(16, (os.cpu_count() or 4) * 2)


def scan(root: str, cancel: threading.Event | None = None, progress=None,
         min_file_size: int = 1 << 20, workers: int = DEFAULT_WORKERS, on_start=None) -> Node:
    """Liest `root` ein – mehrere Ordner parallel. Symlinks/Junctions werden übersprungen.

    Dateien unter `min_file_size` werden pro Ordner zu einem Sammelknoten zusammengefasst,
    damit der Baum auch bei Millionen Dateien klein bleibt.
    `progress(file_count, total_bytes)` wird etwa alle 100 ms aufgerufen.
    `on_start(root_node)` bekommt den Wurzelknoten sofort: Größen darin wachsen live mit,
    Kinder sind aber erst nach Ende sortiert (für eine Vorschau während des Scans).
    """
    root = os.path.abspath(root)
    tree = Node(name=root, path=root, is_dir=True)
    if on_start is not None:
        on_start(tree)

    lock = threading.Lock()
    totals = [0, 0]  # Dateien, Bytes
    outstanding = 1  # Ordner in der Warteschlange oder in Arbeit
    done = threading.Event()
    errors: list[BaseException] = []
    todo: queue.SimpleQueue[Node | None] = queue.SimpleQueue()
    todo.put(tree)

    def read_dir(node: Node) -> list[Node]:
        files = size = small_size = small_count = 0
        subdirs: list[Node] = []
        big: list[Node] = []
        try:
            with os.scandir(node.path) as it:  # Windows: liest ohne GIL, Größe kommt gratis mit
                for entry in it:
                    try:
                        if entry.is_dir(follow_symlinks=False):
                            if not _is_junction(entry):
                                subdirs.append(Node(entry.name, entry.path, is_dir=True, parent=node))
                        elif entry.is_file(follow_symlinks=False):
                            st = entry.stat(follow_symlinks=False)
                            n = 0 if getattr(st, "st_file_attributes", 0) & _CLOUD_ONLY else st.st_size
                            files += 1
                            size += n
                            if n >= min_file_size:
                                big.append(Node(entry.name, entry.path, n, parent=node, file_count=1))
                            else:
                                small_size += n
                                small_count += 1
                    except OSError:
                        continue
        except OSError:
            pass  # kein Zugriff o. Ä.: Ordner bleibt leer
        if small_count:
            big.append(Node(SMALL_FILES_NAME, node.path, small_size, is_aggregate=True,
                            file_count=small_count, parent=node))
        node.children = subdirs + big
        with lock:
            totals[0] += files
            totals[1] += size
            p = node
            while p is not None:  # Summen sofort nach oben tragen -> Live-Vorschau
                p.size += size
                p.file_count += files
                p = p.parent
        return subdirs

    def worker() -> None:
        nonlocal outstanding
        while (node := todo.get()) is not None:
            subdirs: list[Node] = []
            try:
                if not (cancel is not None and cancel.is_set()):
                    subdirs = read_dir(node)
            except BaseException as e:  # unerwartet: merken, im Aufrufer-Thread erneut werfen
                errors.append(e)
            with lock:
                outstanding += len(subdirs) - 1
                finished = outstanding == 0
            for d in subdirs:
                todo.put(d)
            if finished:
                done.set()

    threads = [threading.Thread(target=worker, name="scan", daemon=True) for _ in range(max(1, workers))]
    for t in threads:
        t.start()
    while not done.wait(0.1):
        if progress is not None:
            progress(totals[0], totals[1])
    for _ in threads:
        todo.put(None)
    for t in threads:
        t.join()
    if errors:
        raise errors[0]
    if cancel is not None and cancel.is_set():
        raise ScanCancelled

    stack = [tree]  # iterativ statt rekursiv: auch beliebig tiefe Ordner sind kein Problem
    while stack:
        node = stack.pop()
        node.children.sort(key=lambda n: n.size, reverse=True)
        stack.extend(c for c in node.children if c.is_dir)
    if progress is not None:
        progress(totals[0], totals[1])
    return tree


def replace_subtree(old: Node, new: Node) -> None:
    """Setzt einen neu gescannten Ordner `new` an die Stelle von `old` und korrigiert die Summen darüber."""
    parent = old.parent
    new.name = old.name
    new.parent = parent
    if parent is None:
        return
    parent.children[parent.children.index(old)] = new
    d_size, d_files = new.size - old.size, new.file_count - old.file_count
    node = parent
    while node is not None:
        node.size += d_size
        node.file_count += d_files
        node.children.sort(key=lambda n: n.size, reverse=True)
        node = node.parent


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
