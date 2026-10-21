"""Speicherplatz-Analyse: Ordnerbaum einlesen und als Treemap-Rechtecke anordnen (ohne UI, testbar)."""

import os
import threading
import time
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


# Mehrere Prozesse statt Threads: os.scandir gibt pro Eintrag das GIL frei – mit Threads blockieren
# sich die Leser dadurch gegenseitig (gemessen: 2 Threads ~4x, 8 Threads ~12x langsamer als einer).
DEFAULT_PROCESSES = max(1, min(8, os.cpu_count() or 1))
_FAN_OUT_MIN_DIRS = 8  # weniger Ordner lohnen den Prozess-Pool nicht

_pool = None
_pool_cancel = None
_pool_lock = threading.Lock()
_pool_broken = False
_worker_cancel = None
_tasks_done = 0  # Zähler für Tests: wie viele Ordner im Pool gelesen wurden


def _read_dir(node: Node, min_file_size: int) -> tuple[list[Node], int, int]:
    """Liest einen Ordner: hängt Dateien/Sammelknoten an `node`, liefert (Unterordner, Dateien, Bytes)."""
    files = size = small_size = small_count = 0
    subdirs: list[Node] = []
    big: list[Node] = []
    try:
        with os.scandir(node.path) as it:  # Windows: Größe kommt ohne extra Systemaufruf mit
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
    p = node
    while p is not None:  # Summen sofort nach oben tragen -> Live-Vorschau
        p.size += size
        p.file_count += files
        p = p.parent
    return subdirs, files, size


def _walk(start: Node, cancel, min_file_size: int, totals: list[int] | None = None, progress=None) -> None:
    """Liest `start` samt Unterordnern im aktuellen Prozess (iterativ: beliebige Tiefe)."""
    stack = [start]
    last = 0.0
    while stack:
        if cancel is not None and cancel.is_set():
            return
        subdirs, files, size = _read_dir(stack.pop(), min_file_size)
        stack.extend(subdirs)
        if totals is not None:
            totals[0] += files
            totals[1] += size
            if progress is not None and (now := time.monotonic()) - last > 0.1:
                last = now
                progress(totals[0], totals[1])


def _init_worker(cancel) -> None:
    global _worker_cancel
    _worker_cancel = cancel


def _scan_task(path: str, min_file_size: int) -> list[tuple]:
    """Läuft im Pool-Prozess. Ergebnis flach (Vorordnung, Index des Elternknotens) statt verschachtelt:
    klein beim Übertragen und ohne Rekursionstiefe beim Pickeln."""
    root = Node("", path, is_dir=True)
    _walk(root, _worker_cancel, min_file_size)
    flat: list[tuple] = []
    stack: list[tuple[Node, int]] = [(root, -1)]
    while stack:
        node, parent_idx = stack.pop()
        idx = len(flat)
        flat.append((parent_idx, node.name, node.size, node.is_dir, node.is_aggregate, node.file_count))
        stack.extend((c, idx) for c in node.children)
    return flat


def _graft(target: Node, flat: list[tuple]) -> tuple[int, int]:
    """Baut das Ergebnis von `_scan_task` unter `target` (Platzhalter im Baum) wieder auf."""
    nodes = [target]
    for parent_idx, name, size, is_dir, is_agg, count in flat[1:]:
        parent = nodes[parent_idx]
        path = parent.path if is_agg else os.path.join(parent.path, name)
        node = Node(name, path, size, is_dir, is_agg, count, parent=parent)
        parent.children.append(node)
        nodes.append(node)
    _, _, size, _, _, files = flat[0]
    p = target
    while p is not None:
        p.size += size
        p.file_count += files
        p = p.parent
    return files, size


def _get_pool(processes: int):
    global _pool, _pool_cancel
    from concurrent.futures import ProcessPoolExecutor
    import multiprocessing

    with _pool_lock:
        if _pool is None:
            ctx = multiprocessing.get_context("spawn")  # überall gleich wie unter Windows
            _pool_cancel = ctx.Event()
            _pool = ProcessPoolExecutor(processes, mp_context=ctx, initializer=_init_worker,
                                        initargs=(_pool_cancel,))
        return _pool, _pool_cancel


def shutdown_pool() -> None:
    """Beendet den Prozess-Pool (z. B. beim Schließen der App)."""
    global _pool
    with _pool_lock:
        if _pool is not None:
            _pool_cancel.set()
            _pool.shutdown(wait=False, cancel_futures=True)
            _pool = None


def _fan_out(frontier: list[Node], cancel, progress, min_file_size: int,
             processes: int, totals: list[int]) -> list[Node]:
    """Verteilt Ordner auf den Prozess-Pool. Gibt zurück, was nicht im Pool erledigt wurde."""
    global _pool_broken, _tasks_done
    from concurrent.futures import FIRST_COMPLETED, wait
    from concurrent.futures.process import BrokenProcessPool

    try:
        pool, pool_cancel = _get_pool(processes)
        pool_cancel.clear()
        pending = {pool.submit(_scan_task, n.path, min_file_size): n for n in frontier}
    except Exception:  # z. B. Prozessstart verboten -> im eigenen Prozess weitermachen
        _pool_broken = True
        return frontier
    left: list[Node] = []
    while pending:
        done, _ = wait(pending, timeout=0.1, return_when=FIRST_COMPLETED)
        if cancel is not None and cancel.is_set():
            pool_cancel.set()
            for f in pending:
                f.cancel()
            # Laufende Aufgaben sehen das Signal beim nächsten Ordner; abwarten, damit ein sofort
            # folgender Scan (der das Signal zurücksetzt) sie nicht wieder weiterlaufen lässt.
            wait(pending, timeout=2)
            return []
        for f in done:
            node = pending.pop(f)
            try:
                files, size = _graft(node, f.result())
                _tasks_done += 1
            except BrokenProcessPool:
                _pool_broken = True
                shutdown_pool()
                left.append(node)
                left.extend(pending.values())
                return left
            totals[0] += files
            totals[1] += size
        if progress is not None:
            progress(totals[0], totals[1])
    return left


def scan(root: str, cancel: threading.Event | None = None, progress=None,
         min_file_size: int = 1 << 20, processes: int = DEFAULT_PROCESSES, on_start=None) -> Node:
    """Liest `root` ein, große Bäume parallel in mehreren Prozessen. Symlinks/Junctions werden übersprungen.

    Dateien unter `min_file_size` werden pro Ordner zu einem Sammelknoten zusammengefasst,
    damit der Baum auch bei Millionen Dateien klein bleibt.
    `progress(file_count, total_bytes)` wird regelmäßig aufgerufen.
    `on_start(root_node)` bekommt den Wurzelknoten sofort: Größen darin wachsen live mit,
    Kinder sind aber erst nach Ende sortiert (für eine Vorschau während des Scans).
    """
    root = os.path.abspath(root)
    tree = Node(name=root, path=root, is_dir=True)
    if on_start is not None:
        on_start(tree)
    totals = [0, 0]  # Dateien, Bytes

    def check_cancel() -> None:
        if cancel is not None and cancel.is_set():
            raise ScanCancelled

    # Obere Ebenen hier lesen, bis genug Ordner da sind, um sie auf Prozesse zu verteilen.
    frontier = [tree]
    parallel = processes > 1 and not _pool_broken
    for _ in range(3 if parallel else 0):
        if not frontier or len(frontier) >= processes * 4:
            break
        nxt: list[Node] = []
        for node in frontier:
            check_cancel()
            subdirs, files, size = _read_dir(node, min_file_size)
            nxt += subdirs
            totals[0] += files
            totals[1] += size
        frontier = nxt
        if progress is not None:
            progress(totals[0], totals[1])

    if parallel and len(frontier) >= _FAN_OUT_MIN_DIRS:
        frontier = _fan_out(frontier, cancel, progress, min_file_size, processes, totals)
    for node in frontier:  # Rest (oder alles, wenn nicht parallel) im eigenen Prozess
        _walk(node, cancel, min_file_size, totals, progress)
    check_cancel()

    stack = [tree]  # sortieren, iterativ
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
