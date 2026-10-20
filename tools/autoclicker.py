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
GA_ROOT = 2

if sys.platform == "win32":
    import ctypes
    from ctypes import wintypes

    # Eigene DLL-Instanz, damit unsere argtypes nicht mit pynput kollidieren. Aus jedem Thread nutzbar.
    _user32 = ctypes.WinDLL("user32")
    _user32.WindowFromPoint.argtypes = [wintypes.POINT]
    _user32.WindowFromPoint.restype = wintypes.HWND
    _user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
    _user32.GetAncestor.restype = wintypes.HWND

    def _toplevel_at(x: int, y: int) -> int:
        """Handle des obersten sichtbaren Fensters an (x, y) – berücksichtigt Überdeckung."""
        hit = _user32.WindowFromPoint(wintypes.POINT(x, y))
        return (_user32.GetAncestor(hit, GA_ROOT) or 0) if hit else 0


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
        # Eigenes Event pro Lauf: hängt ein alter Thread noch (join-Timeout), läuft er nicht ungewollt weiter.
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, args=(config, self._stop), daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=1)
            self._thread = None

    def _run(self, config: ClickConfig, stop: threading.Event) -> None:
        button = self._buttons[config.button]
        count = 2 if config.double else 1
        while not stop.is_set():
            target = config.position if config.position is not None else tuple(self._mouse.position)
            if self._is_blocked(target):
                self.waiting = True
                stop.wait(min(config.interval_ms / 1000, self.BLOCKED_RECHECK_S))
                continue
            self.waiting = False
            if config.position is not None:
                self._mouse.position = config.position
            self._mouse.click(button, count)
            self.clicks += 1
            if config.repeat and self.clicks >= config.repeat:
                break
            stop.wait(config.interval_ms / 1000)
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
        self._hwnd = 0  # Fensterhandle des Launchers (Windows), vom Main-Thread gepflegt
        self._toggle_requests: queue.SimpleQueue[None] = queue.SimpleQueue()
        self._hotkey: GlobalHotkey | None = None

        s = self.settings
        self._interval = tk.StringVar(value=str(s.get("interval", "100")))
        self._button = tk.StringVar(value=s.get("button") if s.get("button") in ("left", "middle", "right") else "left")
        self._double = tk.BooleanVar(value=bool(s.get("double", False)))
        self._repeat = tk.StringVar(value=str(s.get("repeat", "0")))
        self._fixed_pos = self._valid_pos(s.get("fixed_pos"))
        self._pos_mode = tk.StringVar(value="fixed" if s.get("pos_mode") == "fixed" and self._fixed_pos else "cursor")
        self._error = tk.StringVar()
        self._root = parent.winfo_toplevel()

        self._build_ui(parent)
        if self._fixed_pos:
            self._pos_label.configure(text=f"x {self._fixed_pos[0]}  ·  y {self._fixed_pos[1]}")
        try:
            self._hotkey = GlobalHotkey(HOTKEY_LABEL, lambda: self._toggle_requests.put(None))
            self._hotkey.start()
        except HotkeyError as e:
            self._hotkey = None
            self._error.set(f"{e} – nutze den Start-Button.")
        self._poll()

    @staticmethod
    def _valid_pos(value) -> tuple[int, int] | None:
        if isinstance(value, (list, tuple)) and len(value) == 2 and all(isinstance(v, int) for v in value):
            return (value[0], value[1])
        return None

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
        self._toggle_btn = ttk.Button(top, text="Start", style="Accent.TButton",
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
        if self._over_own_window((x, y)):
            self._error.set("Der Punkt liegt im werkbank-Fenster – dort wird nicht geklickt.")

    def _over_own_window(self, pos) -> bool:
        # Läuft im Klick-Thread: kein Tk, nur gecachte Werte bzw. thread-sichere WinAPI.
        x, y = (int(v) for v in pos)
        if sys.platform == "win32":
            # Fragt das tatsächlich sichtbare Fenster ab: liegt werkbank verdeckt im Hintergrund, wird geklickt.
            return bool(self._hwnd) and _toplevel_at(x, y) == self._hwnd
        rect = self._window_rect
        if rect is None:
            return False
        left, top, right, bottom = rect
        return left <= x < right and top <= y < bottom

    def _update_window_rect(self) -> None:
        if sys.platform == "win32":
            self._hwnd = int(self._root.wm_frame(), 16)
            return
        if self._root.state() == "iconic":
            self._window_rect = None
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
            hint = "Zielpunkt liegt im Fenster" if self._pos_mode.get() == "fixed" else "Maus aus dem Fenster bewegen"
            status, style = f"● WARTET – {hint}", "Status.TLabel"
        else:
            status, style = "● KLICKT", "StatusOn.TLabel"
        self._status.configure(text=status, style=style)
        label = "Stop" if running else "Start"
        if self._hotkey is not None:
            label += f"  ·  {HOTKEY_LABEL}"
        self._toggle_btn.configure(text=label,
                                   style="Stop.TButton" if running else "Accent.TButton")
        self._root.after(50, self._poll)

    def on_close(self) -> None:
        self._clicker.stop()
        if self._hotkey is not None:
            self._hotkey.stop()
        self.settings.update(interval=self._interval.get(), button=self._button.get(),
                             double=self._double.get(), repeat=self._repeat.get(),
                             pos_mode=self._pos_mode.get(),
                             fixed_pos=list(self._fixed_pos) if self._fixed_pos else None)
