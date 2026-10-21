"""Misst die Scan-Geschwindigkeit: python scripts/bench_scan.py ORDNER [ORDNER ...]

Mit --cold ORDNER1 ORDNER2 …: jede Variante liest einen eigenen, noch nicht gecachten Ordner.
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import diskusage  # noqa: E402
from core.diskusage import scan, shutdown_pool  # noqa: E402


def run(label: str, fn) -> None:
    start = time.perf_counter()
    files = fn()
    secs = time.perf_counter() - start
    print(f"  {label:12s} {secs:7.2f}s  {files:>9,} Dateien  {files / secs:>9,.0f}/s", flush=True)


def main() -> None:
    configs = [(f"{p} Prozess" + ("e" if p > 1 else ""), lambda r, p=p: scan(r, processes=p).file_count)
               for p in (1, 2, 4, 8)]
    args = sys.argv[1:]
    if args and args[0] == "--cold":
        # Gleichartige, noch ungelesene Ordner: jede Variante bekommt einen eigenen, kalten.
        print("kalt (je Variante ein eigener, gleichartiger Ordner)")
        for root, (label, fn) in zip(args[1:], configs):
            run(f"{label}", lambda: fn(root))
            shutdown_pool()
        return
    for root in args:
        print(root)
        for label, fn in configs[:1] + configs:  # erster Lauf wärmt den Cache
            run(label, lambda: fn(root))
            shutdown_pool()  # Pool-Start jedes Mal mitmessen (wie beim ersten Scan nach App-Start)
    print(f"Pool-Aufgaben: {diskusage._tasks_done}, Pool defekt: {diskusage._pool_broken}")


if __name__ == "__main__":
    import multiprocessing
    multiprocessing.freeze_support()
    main()
