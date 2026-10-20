"""werkbank – Launcher für alle Tools in `tools/`."""

import re
import sys
import tkinter as tk
import traceback
from tkinter import messagebox, ttk

from core import theme
from core.registry import Tool, discover_tools
from core.settings import Settings, config_dir


class Launcher:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.settings = Settings()
        self.prefs = self.settings.section("_launcher")
        self.tool_classes = discover_tools()
        self.instances: dict[type[Tool], Tool] = {}
        self.frames: dict[type[Tool], ttk.Frame] = {}
        self.nav_buttons: dict[type[Tool], ttk.Button] = {}
        self.current: type[Tool] | None = None
        self._shown_errors: set[str] = set()

        root.title("werkbank")
        root.geometry(self._saved_size())
        root.minsize(820, 560)
        if self.prefs.get("zoomed") and sys.platform == "win32":
            root.state("zoomed")
        theme.apply(root)
        root.protocol("WM_DELETE_WINDOW", self.close)
        root.report_callback_exception = self.report_error

        sidebar = ttk.Frame(root, style="Sidebar.TFrame", width=190)
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)
        ttk.Label(sidebar, text="werkbank_", style="Brand.TLabel").pack(anchor="w", padx=18, pady=(20, 26))
        ttk.Label(sidebar, text="TOOLS", style="SidebarMuted.TLabel").pack(anchor="w", padx=18, pady=(0, 6))
        for i, cls in enumerate(self.tool_classes):
            btn = ttk.Button(sidebar, text=cls.name, style="Nav.TButton", takefocus=False,
                             command=lambda c=cls: self.show(c))
            btn.pack(fill="x")
            self.nav_buttons[cls] = btn
            if i < 9:  # Strg+1 … Strg+9 wechselt das Tool
                root.bind(f"<Control-Key-{i + 1}>", lambda e, c=cls: self.show(c))

        main = ttk.Frame(root, padding=(36, 28))
        main.pack(side="left", fill="both", expand=True)
        self.title = ttk.Label(main, style="Title.TLabel")
        self.title.pack(anchor="w")
        self.subtitle = ttk.Label(main, style="Muted.TLabel", wraplength=480, justify="left")
        self.subtitle.pack(anchor="w", pady=(2, 24))
        self.content = ttk.Frame(main)
        self.content.pack(fill="both", expand=True)

        # Alle Tools sofort bauen, damit z. B. der F6-Hotkey auch gilt, bevor der Autoklicker geöffnet wurde.
        for cls in self.tool_classes:
            self._build(cls)

        if self.tool_classes:
            last = next((c for c in self.tool_classes if c.name == self.prefs.get("last_tool")), None)
            self.show(last or self.tool_classes[0])
        else:
            self.title.configure(text="Keine Tools gefunden")
            self.subtitle.configure(text="Lege eine Datei in tools/ an, die von core.registry.Tool erbt.")

    def _saved_size(self) -> str:
        size = self.prefs.get("size")
        if isinstance(size, str) and re.fullmatch(r"\d{3,5}x\d{3,5}", size):
            return size
        return "1040x660"

    def _build(self, cls: type[Tool]) -> None:
        frame = ttk.Frame(self.content)
        self.frames[cls] = frame
        try:
            tool = cls()
            tool.settings = self.settings.section(cls.__name__)
            self.instances[cls] = tool  # auch bei Fehler in build(), damit on_close() aufräumen kann
            tool.build(frame)
        except Exception as e:
            traceback.print_exc()
            for child in frame.winfo_children():
                child.destroy()
            ttk.Label(frame, text=f"Tool konnte nicht gestartet werden:\n{type(e).__name__}: {e}",
                      foreground=theme.DANGER, justify="left").pack(anchor="w")

    def show(self, cls: type[Tool]) -> None:
        if self.current is not None:
            self.frames[self.current].pack_forget()
            self.nav_buttons[self.current].configure(style="Nav.TButton")
        self.frames[cls].pack(fill="both", expand=True)
        self.nav_buttons[cls].configure(style="NavActive.TButton")
        self.title.configure(text=cls.name)
        self.subtitle.configure(text=cls.description)
        self.current = cls

    def report_error(self, exc_type, exc, tb) -> None:
        """Fehler in Tk-Callbacks: ins Log schreiben und (einmal pro Fehlerart) anzeigen statt stumm verschlucken."""
        traceback.print_exception(exc_type, exc, tb)
        key = f"{exc_type.__name__}: {exc}"
        if key not in self._shown_errors:
            self._shown_errors.add(key)
            messagebox.showerror("werkbank – Fehler", f"{key}\n\nDetails: {config_dir() / 'werkbank.log'}",
                                 parent=self.root)

    def close(self) -> None:
        for tool in self.instances.values():
            try:
                tool.on_close()
            except Exception as e:
                print(f"[werkbank] Fehler beim Schließen von {tool.name}: {e}")
        zoomed = self.root.state() == "zoomed"
        self.prefs["zoomed"] = zoomed
        if not zoomed:
            self.prefs["size"] = f"{self.root.winfo_width()}x{self.root.winfo_height()}"
        if self.current is not None:
            self.prefs["last_tool"] = self.current.name
        self.settings.save()
        self.root.destroy()


def _redirect_output_if_windowless() -> None:
    # Unter pythonw.exe gibt es keine Konsole – Ausgaben/Tracebacks sonst spurlos weg.
    if sys.stdout is not None and sys.stderr is not None:
        return
    try:
        log_dir = config_dir()
        log_dir.mkdir(parents=True, exist_ok=True)
        log = open(log_dir / "werkbank.log", "a", encoding="utf-8", buffering=1)
    except OSError:
        return
    sys.stdout = sys.stdout or log
    sys.stderr = sys.stderr or log


def main() -> None:
    _redirect_output_if_windowless()
    if sys.platform == "win32":
        # Echte Pixel-Koordinaten, damit Mausposition und Bildschirm übereinstimmen.
        import ctypes
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:
            pass
    root = tk.Tk()
    Launcher(root)
    root.mainloop()


if __name__ == "__main__":
    main()
