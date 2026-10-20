"""Autoklicker: klickt in festem Intervall, global per F6 start-/stoppbar."""

import queue
import sys
import threading
import tkinter as tk
from dataclasses import dataclass
from tkinter import ttk

from core import theme
from core.hotkey import GlobalHotkey, HotkeyError
from core.registry import Tool

HOTKEY_LABEL = "F6"
PICK_COUNTDOWN_S = 3


@dataclass(frozen=True)
class ClickConfig:
    interval_ms: int = 100
    button: str = "left"  # left | right | middle
    double: bool = False
    repeat: int = 0  # 0 = endlos
    position: tuple[int, int] | None = None  # None = aktuelle Mausposition

    def __post_init__(self):
        if self.interval_ms < 1:
            raise ValueError("Intervall muss mindestens 1 ms sein")
        if self.repeat < 0:
            raise ValueError("Wiederholungen dürfen nicht negativ sein")
        if self.button not in ("left", "right", "middle"):
            raise ValueError(f"Unbekannte Maustaste: {self.button}")


class Clicker:
    """Klick-Schleife in eigenem Thread. `mouse` braucht `.position` und `.click(button, count)`.

    `is_blocked(pos)` → True heißt: an dieser Stelle nicht klicken, sondern warten
    (z. B. weil dort das eigene Fenster liegt).
    """

    BLOCKED_RECHECK_S = 0.05

    def __init__(self, mouse, buttons: dict, is_blocked=lambda pos: False):
        self._mouse = mouse
        self._buttons = buttons
        self._is_blocked = is_blocked
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.clicks = 0
        self.waiting = False

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self, config: ClickConfig) -> None:
        self.stop()
        self.clicks = 0
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, args=(config,), daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=1)
            self._thread = None

    def _run(self, config: ClickConfig) -> None:
        button = self._buttons[config.button]
        count = 2 if config.double else 1
        while not self._stop.is_set():
            target = config.position if config.position is not None else tuple(self._mouse.position)
            if self._is_blocked(target):
                self.waiting = True
                self._stop.wait(min(config.interval_ms / 1000, self.BLOCKED_RECHECK_S))
                continue
            self.waiting = False
            if config.position is not None:
                self._mouse.position = config.position
            self._mouse.click(button, count)
            self.clicks += 1
            if config.repeat and self.clicks >= config.repeat:
                break
            self._stop.wait(config.interval_ms / 1000)
        self.waiting = False


class AutoClicker(Tool):
    name = "Autoklicker"
    description = f"Klickt automatisch im Intervall. {HOTKEY_LABEL} startet und stoppt – auch wenn das Fenster im Hintergrund ist."

    def build(self, parent: ttk.Frame) -> None:
        from pynput import mouse

        self._mouse = mouse.Controller()
        self._window_rect: tuple[int, int, int, int] | None = None
        self._clicker = Clicker(self._mouse, {
            "left": mouse.Button.left, "right": mouse.Button.right, "middle": mouse.Button.middle,
        }, is_blocked=self._over_own_window)
        self._toggle_requests: queue.SimpleQueue[None] = queue.SimpleQueue()
        self._hotkey = GlobalHotkey(HOTKEY_LABEL, lambda: self._toggle_requests.put(None))

        self._interval = tk.StringVar(value="100")
        self._button = tk.StringVar(value="left")
        self._double = tk.BooleanVar(value=False)
        self._repeat = tk.StringVar(value="0")
        self._pos_mode = tk.StringVar(value="cursor")
        self._fixed_pos: tuple[int, int] | None = None
        self._error = tk.StringVar()
        self._root = parent.winfo_toplevel()

        self._build_ui(parent)
        try:
            self._hotkey.start()
        except HotkeyError as e:
            self._hotkey = None
            self._error.set(f"{e} – nutze den Start-Button.")
        self._poll()

    # ---------- UI ----------

    def _build_ui(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(0, weight=1)

        # Anzeige: Zähler + Status + Start/Stop
        top = ttk.Frame(parent)
        top.grid(row=0, column=0, sticky="ew", pady=(0, 22))
        top.columnconfigure(0, weight=1)
        self._status = ttk.Label(top, text="● BEREIT", style="Status.TLabel")
        self._status.grid(row=0, column=0, sticky="w")
        self._counter = ttk.Label(top, text="0", style="Big.TLabel")
        self._counter.grid(row=1, column=0, sticky="w")
        ttk.Label(top, text="Klicks in diesem Lauf", style="Muted.TLabel").grid(row=2, column=0, sticky="w")
        self._toggle_btn = ttk.Button(top, text=f"Start  ·  {HOTKEY_LABEL}", style="Accent.TButton",
                                      command=self._toggle, takefocus=False)
        self._toggle_btn.grid(row=0, column=1, rowspan=3, sticky="e")

        ttk.Separator(parent).grid(row=1, column=0, sticky="ew", pady=(0, 18))

        form = ttk.Frame(parent)
        form.grid(row=2, column=0, sticky="ew")
        form.columnconfigure(1, weight=1)
        row = 0

        def section(text, sticky="w"):
            ttk.Label(form, text=text.upper(), style="Section.TLabel").grid(
                row=row, column=0, sticky=sticky, pady=(0, 14), padx=(0, 24))

        section("Intervall")
        box = ttk.Frame(form)
        box.grid(row=row, column=1, sticky="w", pady=(0, 14))
        ttk.Spinbox(box, from_=1, to=3_600_000, increment=10, width=9,
                    textvariable=self._interval).pack(side="left")
        ttk.Label(box, text="ms", style="Muted.TLabel").pack(side="left", padx=(8, 0))
        row += 1

        section("Taste")
        seg = ttk.Frame(form, style="Surface.TFrame")
        seg.grid(row=row, column=1, sticky="w", pady=(0, 14))
        for value, label in (("left", "Links"), ("middle", "Mitte"), ("right", "Rechts")):
            ttk.Radiobutton(seg, text=label, value=value, variable=self._button,
                            style="Seg.TRadiobutton", takefocus=False).pack(side="left")
        ttk.Checkbutton(form, text="Doppelklick", variable=self._double, takefocus=False).grid(
            row=row, column=1, sticky="e", pady=(0, 14))
        row += 1

        section("Anzahl")
        box = ttk.Frame(form)
        box.grid(row=row, column=1, sticky="w", pady=(0, 14))
        ttk.Spinbox(box, from_=0, to=1_000_000, increment=1, width=9,
                    textvariable=self._repeat).pack(side="left")
        ttk.Label(box, text="0 = endlos", style="Muted.TLabel").pack(side="left", padx=(8, 0))
        row += 1

        section("Position", sticky="nw")
        box = ttk.Frame(form)
        box.grid(row=row, column=1, sticky="w")
        ttk.Radiobutton(box, text="Mauszeiger folgen", value="cursor", variable=self._pos_mode,
                        takefocus=False).pack(anchor="w")
        fixed = ttk.Frame(box)
        fixed.pack(anchor="w", pady=(6, 0))
        ttk.Radiobutton(fixed, text="Fester Punkt", value="fixed", variable=self._pos_mode,
                        takefocus=False).pack(side="left")
        self._pick_btn = ttk.Button(fixed, text="Punkt wählen", command=self._pick_position,
                                    takefocus=False)
        self._pick_btn.pack(side="left", padx=(12, 8))
        self._pos_label = ttk.Label(fixed, text="—", style="Muted.TLabel", font=(theme.MONO, 9))
        self._pos_label.pack(side="left")

        ttk.Label(parent, textvariable=self._error, foreground=theme.DANGER).grid(
            row=3, column=0, sticky="w", pady=(18, 0))

    # ---------- Logik ----------

    def _read_config(self) -> ClickConfig:
        try:
            interval = int(self._interval.get())
            repeat = int(self._repeat.get())
        except ValueError:
            raise ValueError("Intervall und Anzahl müssen ganze Zahlen sein")
        position = None
        if self._pos_mode.get() == "fixed":
            if self._fixed_pos is None:
                raise ValueError("Erst einen festen Punkt wählen")
            position = self._fixed_pos
        return ClickConfig(interval_ms=interval, button=self._button.get(),
                           double=self._double.get(), repeat=repeat, position=position)

    def _toggle(self) -> None:
        if self._clicker.running:
            self._clicker.stop()
            return
        try:
            config = self._read_config()
        except ValueError as e:
            self._error.set(str(e))
            return
        self._error.set("")
        self._clicker.start(config)

    def _pick_position(self, remaining: int = PICK_COUNTDOWN_S) -> None:
        if remaining > 0:
            self._pick_btn.state(["disabled"])
            self._pos_label.configure(text=f"Maus hinbewegen … {remaining}")
            self._root.after(1000, self._pick_position, remaining - 1)
            return
        x, y = (int(v) for v in self._mouse.position)
        self._fixed_pos = (x, y)
        self._pos_mode.set("fixed")
        self._pos_label.configure(text=f"x {x}  ·  y {y}")
        self._pick_btn.state(["!disabled"])

    def _over_own_window(self, pos) -> bool:
        # Läuft im Klick-Thread: nur das gecachte Rechteck lesen, kein Tk.
        rect = self._window_rect
        if rect is None:
            return False
        left, top, right, bottom = rect
        x, y = pos
        return left <= x < right and top <= y < bottom

    def _update_window_rect(self) -> None:
        if self._root.state() == "iconic":
            self._window_rect = None
            return
        if sys.platform == "win32":
            import ctypes
            from ctypes import wintypes
            r = wintypes.RECT()
            hwnd = int(self._root.wm_frame(), 16)
            if ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(r)):
                self._window_rect = (r.left, r.top, r.right, r.bottom)
                return
        x, y = self._root.winfo_rootx(), self._root.winfo_rooty()
        self._window_rect = (x, y, x + self._root.winfo_width(), y + self._root.winfo_height())

    def _poll(self) -> None:
        # Hotkey kommt aus dem Listener-Thread; Tk-Zugriffe nur hier im Main-Thread.
        self._update_window_rect()
        while True:
            try:
                self._toggle_requests.get_nowait()
            except queue.Empty:
                break
            self._toggle()
        running = self._clicker.running
        self._counter.configure(text=f"{self._clicker.clicks:,}".replace(",", "."))
        if not running:
            status, style = "● BEREIT", "Status.TLabel"
        elif self._clicker.waiting:
            status, style = "● WARTET – Maus aus dem Fenster bewegen", "Status.TLabel"
        else:
            status, style = "● KLICKT", "StatusOn.TLabel"
        self._status.configure(text=status, style=style)
        self._toggle_btn.configure(text=f"{'Stop' if running else 'Start'}  ·  {HOTKEY_LABEL}",
                                   style="Stop.TButton" if running else "Accent.TButton")
        self._root.after(50, self._poll)

    def on_close(self) -> None:
        self._clicker.stop()
        if self._hotkey is not None:
            self._hotkey.stop()
