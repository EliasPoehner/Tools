"""Speicher-Explorer: zeigt als Treemap, welche Ordner und Dateien wie viel Platz belegen."""

import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, ttk

from core import theme
from core.diskusage import Node, ScanCancelled, format_size, scan, squarify
from core.registry import Tool

# gedeckte Farben, die zum dunklen Bernstein-Look passen
PALETTE = ["#d9893a", "#4f9d8c", "#7f8fd1", "#c4636f", "#9bb55a", "#b07fc4",
           "#d4b04a", "#5aa2c7", "#c98b6b", "#6fb38a", "#a3a3b8", "#cf7aa3"]
AGGREGATE_COLOR = "#4a4d53"
MIN_TILE_PX = 3  # kleinere Kacheln werden nicht gezeichnet
MAX_TILES = 400


class Speicher(Tool):
    name = "Speicher"
    description = "Zeigt grafisch, welche Ordner und Dateien wie viel Platz belegen. Klick auf eine Kachel öffnet den Ordner."

    def build(self, parent: ttk.Frame) -> None:
        self.parent = parent
        self.root_node: Node | None = None
        self.current: Node | None = None
        self.items: list[Node] = []
        self.tile_nodes: dict[int, Node] = {}
        self.cancel = threading.Event()
        self.thread: threading.Thread | None = None
        self.results: queue.Queue = queue.Queue()
        self.progress = (0, 0)
        self.scanning = False

        top = ttk.Frame(parent)
        top.pack(fill="x")
        self.path_var = tk.StringVar(value=str(Path.home()))
        ttk.Entry(top, textvariable=self.path_var).pack(side="left", fill="x", expand=True, ipady=3)
        ttk.Button(top, text="Ordner…", command=self.choose).pack(side="left", padx=(6, 0))
        self.scan_btn = ttk.Button(top, text="Scannen", style="Accent.TButton", command=self.toggle_scan)
        self.scan_btn.pack(side="left", padx=(6, 0))

        nav = ttk.Frame(parent)
        nav.pack(fill="x", pady=(10, 6))
        self.up_btn = ttk.Button(nav, text="↑ Hoch", command=self.go_up, state="disabled")
        self.up_btn.pack(side="left")
        self.open_btn = ttk.Button(nav, text="Im Explorer", command=self.open_in_explorer, state="disabled")
        self.open_btn.pack(side="left", padx=(6, 0))
        self.crumb = ttk.Label(nav, text="", style="Muted.TLabel")
        self.crumb.pack(side="left", padx=12)

        body = ttk.Frame(parent)
        body.pack(fill="both", expand=True)
        side = ttk.Frame(body, width=250)
        side.pack(side="right", fill="y", padx=(10, 0))
        side.pack_propagate(False)
        self.tree = ttk.Treeview(side, columns=("size", "pct"), show="tree", selectmode="browse")
        self.tree.column("#0", width=130, stretch=True)
        self.tree.column("size", width=70, anchor="e", stretch=False)
        self.tree.column("pct", width=40, anchor="e", stretch=False)
        self.tree.pack(fill="both", expand=True)
        self.tree.bind("<Double-1>", self.on_list_open)
        self.tree.bind("<<TreeviewSelect>>", self.on_list_select)

        self.canvas = tk.Canvas(body, bg=theme.BG, highlightthickness=0)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.canvas.bind("<Configure>", lambda e: self.draw())
        self.canvas.bind("<Motion>", self.on_hover)
        self.canvas.bind("<Leave>", lambda e: self.set_info(self.default_info()))
        self.canvas.bind("<Button-1>", self.on_canvas_click)

        self.info = ttk.Label(parent, text="Ordner wählen und auf „Scannen“ klicken.", style="Muted.TLabel")
        self.info.pack(anchor="w", pady=(8, 0))
        self.selected: Node | None = None

    # --- Scan -------------------------------------------------------------

    def choose(self) -> None:
        folder = filedialog.askdirectory(initialdir=self.path_var.get() or None)
        if folder:
            self.path_var.set(os.path.normpath(folder))
            self.toggle_scan() if not self.scanning else None

    def toggle_scan(self) -> None:
        if self.scanning:
            self.cancel.set()
            return
        path = self.path_var.get().strip()
        if not os.path.isdir(path):
            self.set_info(f"„{path}“ ist kein Ordner.")
            return
        self.cancel = threading.Event()
        self.progress = (0, 0)
        self.scanning = True
        self.scan_btn.configure(text="Abbrechen", style="Stop.TButton")
        cancel = self.cancel

        def work():
            try:
                tree = scan(path, cancel, progress=lambda f, b: setattr(self, "progress", (f, b)))
                self.results.put(("done", tree))
            except ScanCancelled:
                self.results.put(("cancelled", None))
            except Exception as e:  # nie den Thread stumm sterben lassen
                self.results.put(("error", str(e)))

        self.thread = threading.Thread(target=work, daemon=True)
        self.thread.start()
        self.parent.after(150, self.poll)

    def poll(self) -> None:
        try:
            kind, payload = self.results.get_nowait()
        except queue.Empty:
            files, size = self.progress
            self.set_info(f"Scanne … {files:,} Dateien, {format_size(size)}".replace(",", "."))
            self.parent.after(150, self.poll)
            return
        self.scanning = False
        self.scan_btn.configure(text="Scannen", style="Accent.TButton")
        if kind == "done":
            self.root_node = payload
            self.show(payload)
        elif kind == "cancelled":
            self.set_info("Scan abgebrochen.")
        else:
            self.set_info(f"Fehler beim Scannen: {payload}")

    # --- Anzeige ----------------------------------------------------------

    def show(self, node: Node) -> None:
        self.current = node
        self.selected = None
        self.items = [c for c in node.children if c.size > 0]
        self.up_btn.configure(state="normal" if node.parent is not None else "disabled")
        self.open_btn.configure(state="normal")
        self.crumb.configure(text=f"{node.path}  ·  {format_size(node.size)}")
        self.tree.delete(*self.tree.get_children())
        total = node.size or 1
        for i, child in enumerate(self.items):
            label = child.name if (child.is_aggregate or not child.is_dir) else f"📁 {child.name}"
            pct = f"{child.size / total * 100:.0f}%" if child.size / total >= 0.01 else "<1%"
            self.tree.insert("", "end", iid=str(i), text=label, values=(format_size(child.size), pct))
        self.draw()
        self.set_info(self.default_info())

    def default_info(self) -> str:
        if self.current is None:
            return "Ordner wählen und auf „Scannen“ klicken."
        return (f"{self.current.file_count:,} Dateien · {format_size(self.current.size)} "
                "· Klick auf Kachel = Ordner öffnen").replace(",", ".")

    def set_info(self, text: str) -> None:
        self.info.configure(text=text)

    def color_for(self, index: int, node: Node) -> str:
        return AGGREGATE_COLOR if node.is_aggregate else PALETTE[index % len(PALETTE)]

    def draw(self) -> None:
        c = self.canvas
        c.delete("all")
        self.tile_nodes.clear()
        if self.current is None or not self.items:
            if self.current is not None:
                c.create_text(10, 10, anchor="nw", fill=theme.MUTED, text="Dieser Ordner ist leer.")
            return
        w, h = c.winfo_width(), c.winfo_height()
        items = self.items[:MAX_TILES]
        rects = squarify([n.size for n in items], 0, 0, w, h)
        for i, (node, (x, y, rw, rh)) in enumerate(zip(items, rects)):
            if rw < MIN_TILE_PX or rh < MIN_TILE_PX:
                continue
            fill = self.color_for(i, node)
            outline = theme.ACCENT if node is self.selected else theme.BG
            rid = c.create_rectangle(x, y, x + rw, y + rh, fill=fill, outline=outline,
                                     width=3 if node is self.selected else 1)
            self.tile_nodes[rid] = node
            if rw > 70 and rh > 34:
                name = node.name if len(node.name) < max(6, int(rw / 7)) else node.name[: max(5, int(rw / 7)) - 1] + "…"
                tid = c.create_text(x + 7, y + 6, anchor="nw", fill="#15110a", text=name,
                                    font=(theme.FONT, 9, "bold"), width=rw - 12)
                sid = c.create_text(x + 7, y + 22, anchor="nw", fill="#2a2216", text=format_size(node.size),
                                    font=(theme.MONO, 8))
                self.tile_nodes[tid] = node
                self.tile_nodes[sid] = node

    def node_at(self, event) -> Node | None:
        hit = self.canvas.find_overlapping(event.x, event.y, event.x, event.y)
        for item in reversed(hit):
            if item in self.tile_nodes:
                return self.tile_nodes[item]
        return None

    def on_hover(self, event) -> None:
        node = self.node_at(event)
        if node is None:
            self.set_info(self.default_info())
            return
        total = self.current.size or 1
        kind = "Ordner" if node.is_dir else ("Sammlung" if node.is_aggregate else "Datei")
        extra = f" · {node.file_count:,} Dateien".replace(",", ".") if node.file_count > 1 else ""
        self.set_info(f"{node.name} ({kind}) · {format_size(node.size)} · {node.size / total * 100:.1f}%{extra}")

    def on_canvas_click(self, event) -> None:
        node = self.node_at(event)
        if node is None:
            return
        if node.is_dir:
            self.show(node)
        else:
            self.selected = node
            self.sync_list_selection()
            self.draw()

    def on_list_select(self, _event) -> None:
        sel = self.tree.selection()
        if sel:
            self.selected = self.items[int(sel[0])]
            self.draw()

    def on_list_open(self, _event) -> None:
        sel = self.tree.selection()
        if sel and self.items[int(sel[0])].is_dir:
            self.show(self.items[int(sel[0])])

    def sync_list_selection(self) -> None:
        if self.selected in self.items:
            self.tree.selection_set(str(self.items.index(self.selected)))

    def go_up(self) -> None:
        if self.current is not None and self.current.parent is not None:
            self.show(self.current.parent)

    def open_in_explorer(self) -> None:
        target = self.selected or self.current
        if target is None:
            return
        path = target.path
        try:
            if sys.platform == "win32":
                if target.is_dir or target.is_aggregate:
                    os.startfile(path)
                else:
                    subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])
            elif sys.platform == "darwin":
                subprocess.Popen(["open", path if os.path.isdir(path) else os.path.dirname(path)])
            else:
                subprocess.Popen(["xdg-open", path if os.path.isdir(path) else os.path.dirname(path)])
        except OSError as e:
            self.set_info(f"Konnte Explorer nicht öffnen: {e}")

    def on_close(self) -> None:
        self.cancel.set()
