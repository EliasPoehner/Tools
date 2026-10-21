"""Misst die Scan-Geschwindigkeit: python scripts/bench_scan.py ORDNER [ORDNER ...]

Mit --cold ORDNER1 ORDNER2 …: jede Variante liest einen eigenen, noch nicht gecachten Ordner.
"""

import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.diskusage import scan  # noqa: E402


def _scan_one(path: str):
    return scan(path, workers=1)


def scan_processes(root: str, procs: int):
    """Prototyp: Unterordner der 2. Ebene auf Prozesse verteilen (nur Messung, ohne Zusammenbau)."""
    tasks = []
    for e in os.scandir(root):
        if e.is_dir(follow_symlinks=False):
            try:
                tasks += [s.path for s in os.scandir(e.path) if s.is_dir(follow_symlinks=False)]
            except OSError:
                pass
    with ProcessPoolExecutor(procs) as ex:
        return sum(t.file_count for t in ex.map(_scan_one, tasks, chunksize=4))


def run(label: str, fn) -> None:
    start = time.perf_counter()
    files = fn()
    secs = time.perf_counter() - start
    print(f"  {label:12s} {secs:7.2f}s  {files:>9,} Dateien  {files / secs:>9,.0f}/s", flush=True)


def main() -> None:
    configs = [("1 Thread", lambda r: scan(r, workers=1).file_count)]
    configs += [(f"{w} Threads", lambda r, w=w: scan(r, workers=w).file_count) for w in (2, 4, 8)]
    configs += [(f"{p} Prozesse", lambda r, p=p: scan_processes(r, p)) for p in (2, 4)]
    args = sys.argv[1:]
    if args and args[0] == "--cold":
        # Gleichartige, noch ungelesene Ordner: jede Variante bekommt einen eigenen, kalten.
        print("kalt (je Variante ein eigener, gleichartiger Ordner)")
        for root, (label, fn) in zip(args[1:], configs):
            run(f"{label}", lambda: fn(root))
        return
    for root in args:
        print(root)
        for label, fn in configs[:1] + configs:  # erster Lauf wärmt den Cache
            run(label, lambda: fn(root))


if __name__ == "__main__":
    main()
