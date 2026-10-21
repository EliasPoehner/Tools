import os
import threading

import pytest

from core import diskusage
from core.diskusage import SMALL_FILES_NAME, ScanCancelled, format_count, format_size, replace_subtree, scan, squarify


def make_tree(tmp_path):
    (tmp_path / "gross").mkdir()
    (tmp_path / "gross" / "a.bin").write_bytes(b"x" * 3000)
    (tmp_path / "gross" / "b.bin").write_bytes(b"x" * 2000)
    (tmp_path / "klein").mkdir()
    (tmp_path / "klein" / "c.txt").write_bytes(b"x" * 500)
    (tmp_path / "leer").mkdir()
    (tmp_path / "root.txt").write_bytes(b"x" * 100)


def test_sizes_add_up(tmp_path):
    make_tree(tmp_path)
    tree = scan(str(tmp_path), min_file_size=1000)
    assert tree.size == 5600
    assert tree.file_count == 4
    by_name = {c.name: c for c in tree.children}
    assert by_name["gross"].size == 5000
    assert by_name["klein"].size == 500
    assert by_name["leer"].size == 0


def test_small_files_are_aggregated(tmp_path):
    make_tree(tmp_path)
    tree = scan(str(tmp_path), min_file_size=1000)
    names = [c.name for c in tree.children]
    assert SMALL_FILES_NAME in names  # root.txt
    gross = next(c for c in tree.children if c.name == "gross")
    assert {c.name for c in gross.children} == {"a.bin", "b.bin"}


def test_children_sorted_desc_and_parent_set(tmp_path):
    make_tree(tmp_path)
    tree = scan(str(tmp_path), min_file_size=1000)
    sizes = [c.size for c in tree.children]
    assert sizes == sorted(sizes, reverse=True)
    assert all(c.parent is tree for c in tree.children)


def test_cancel(tmp_path):
    make_tree(tmp_path)
    ev = threading.Event()
    ev.set()
    with pytest.raises(ScanCancelled):
        scan(str(tmp_path), cancel=ev)


def test_missing_folder_gives_empty_node(tmp_path):
    tree = scan(str(tmp_path / "gibt-es-nicht"))
    assert tree.size == 0 and tree.children == []


def test_squarify_fills_area_without_overlap():
    values = [60, 30, 20, 10, 5, 5]
    rects = squarify(values, 0, 0, 400, 300)
    assert len(rects) == len(values)
    assert sum(w * h for _, _, w, h in rects) == pytest.approx(400 * 300)
    for x, y, w, h in rects:
        assert x >= -1e-6 and y >= -1e-6 and x + w <= 400 + 1e-6 and y + h <= 300 + 1e-6
    # Flächen proportional zu den Werten
    total = sum(values)
    for v, (_, _, w, h) in zip(values, rects):
        assert w * h == pytest.approx(v / total * 400 * 300)


def test_squarify_edge_cases():
    assert squarify([], 0, 0, 10, 10) == []
    assert squarify([1], 0, 0, 0, 10) == []
    assert squarify([5], 0, 0, 10, 10) == [(0, 0, 10, 10)]


def test_format_size():
    assert format_size(0) == "0 B"
    assert format_size(1023) == "1023 B"
    assert format_size(1536) == "1,5 KB"
    assert format_size(5 * 1024**3) == "5,0 GB"


def test_replace_subtree_updates_totals(tmp_path):
    make_tree(tmp_path)
    tree = scan(str(tmp_path), min_file_size=1000)
    gross = next(c for c in tree.children if c.name == "gross")
    (tmp_path / "gross" / "a.bin").unlink()
    (tmp_path / "gross" / "neu.bin").write_bytes(b"x" * 9000)
    fresh = scan(gross.path, min_file_size=1000)
    replace_subtree(gross, fresh)
    assert fresh.parent is tree and fresh.name == "gross"
    assert gross not in tree.children
    assert fresh.size == 11000
    assert tree.size == 5600 - 3000 + 9000
    assert tree.file_count == 4
    sizes = [c.size for c in tree.children]
    assert sizes == sorted(sizes, reverse=True)


def test_replace_root_keeps_it_root(tmp_path):
    make_tree(tmp_path)
    old = scan(str(tmp_path))
    new = scan(str(tmp_path))
    replace_subtree(old, new)
    assert new.parent is None


def test_format_count():
    assert format_count(7) == "7"
    assert format_count(1234567) == "1.234.567"


def make_wide_tree(tmp_path, dirs=12):
    for d in range(dirs):
        for s in range(3):
            sub = tmp_path / f"d{d}" / f"s{s}" / "tief"
            sub.mkdir(parents=True)
            (sub / "gross.bin").write_bytes(b"x" * (2000 + d * 10 + s))
            (sub.parent / "klein.txt").write_bytes(b"x" * (d + 1))
    (tmp_path / "wurzel.bin").write_bytes(b"x" * 5000)


def flatten(node, base):
    rows = []
    stack = [node]
    while stack:
        n = stack.pop()
        rows.append((os.path.relpath(n.path, base), n.name, n.size, n.is_dir, n.is_aggregate, n.file_count,
                     n.parent.path if n.parent else None))
        stack.extend(n.children)
    return sorted(rows, key=repr)


def test_parallel_scan_equals_sequential(tmp_path):
    make_wide_tree(tmp_path)
    seq = scan(str(tmp_path), min_file_size=1000, processes=1)
    tasks_before = diskusage._tasks_done
    par = scan(str(tmp_path), min_file_size=1000, processes=2)
    assert not diskusage._pool_broken
    assert diskusage._tasks_done - tasks_before == 12  # alle 12 Ordner liefen im Pool
    assert flatten(par, tmp_path) == flatten(seq, tmp_path)
    assert par.size == seq.size and par.file_count == 12 * 3 * 2 + 1
    stack = [par]
    while stack:  # überall absteigend sortiert
        n = stack.pop()
        sizes = [c.size for c in n.children]
        assert sizes == sorted(sizes, reverse=True)
        stack.extend(n.children)


def test_parallel_scan_reports_live_root_and_progress(tmp_path):
    make_wide_tree(tmp_path)
    started, calls = [], []
    tree = scan(str(tmp_path), min_file_size=1000, processes=2, on_start=started.append,
                progress=lambda f, b: calls.append((f, b)))
    assert started == [tree]
    assert calls[-1] == (tree.file_count, tree.size)


def test_parallel_cancel(tmp_path):
    make_wide_tree(tmp_path)
    ev = threading.Event()
    ev.set()
    with pytest.raises(ScanCancelled):
        scan(str(tmp_path), cancel=ev, processes=2)

