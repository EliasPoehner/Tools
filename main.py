"""werkbank – Launcher für alle Tools in `tools/`."""

import sys
import tkinter as tk
from tkinter import ttk

from core import theme
from core.registry import Tool, discover_tools


class Launcher:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.tool_classes = discover_tools()
        self.instances: dict[type[Tool], Tool] = {}
        self.frames: dict[type[Tool], ttk.Frame] = {}
        self.nav_buttons: dict[type[Tool], ttk.Button] = {}
        self.current: type[Tool] | None = None

        root.title("werkbank")
        root.geometry("1040x660")
        root.minsize(820, 560)
        theme.apply(root)
        root.protocol("WM_DELETE_WINDOW", self.close)

        sidebar = ttk.Frame(root, style="Sidebar.TFrame", width=190)
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)
        ttk.Label(sidebar, text="werkbank_", style="Brand.TLabel").pack(anchor="w", padx=18, pady=(20, 26))
        ttk.Label(sidebar, text="TOOLS", style="SidebarMuted.TLabel").pack(anchor="w", padx=18, pady=(0, 6))
        for cls in self.tool_classes:
            btn = ttk.Button(sidebar, text=cls.name, style="Nav.TButton", takefocus=False,
                             command=lambda c=cls: self.show(c))
            btn.pack(fill="x")
            self.nav_buttons[cls] = btn

        main = ttk.Frame(root, padding=(36, 28))
        main.pack(side="left", fill="both", expand=True)
        self.title = ttk.Label(main, style="Title.TLabel")
        self.title.pack(anchor="w")
        self.subtitle = ttk.Label(main, style="Muted.TLabel", wraplength=480, justify="left")
        self.subtitle.pack(anchor="w", pady=(2, 24))
        self.content = ttk.Frame(main)
        self.content.pack(fill="both", expand=True)

        if self.tool_classes:
            self.show(self.tool_classes[0])
        else:
            self.title.configure(text="Keine Tools gefunden")
            self.subtitle.configure(text="Lege eine Datei in tools/ an, die von core.registry.Tool erbt.")

    def show(self, cls: type[Tool]) -> None:
        if self.current is not None:
            self.frames[self.current].pack_forget()
            self.nav_buttons[self.current].configure(style="Nav.TButton")
        if cls not in self.frames:
            frame = ttk.Frame(self.content)
            tool = cls()
            tool.build(frame)
            self.instances[cls] = tool
            self.frames[cls] = frame
        self.frames[cls].pack(fill="both", expand=True)
        self.nav_buttons[cls].configure(style="NavActive.TButton")
        self.title.configure(text=cls.name)
        self.subtitle.configure(text=cls.description)
        self.current = cls

    def close(self) -> None:
        for tool in self.instances.values():
            try:
                tool.on_close()
            except Exception as e:
                print(f"[werkbank] Fehler beim Schließen von {tool.name}: {e}")
        self.root.destroy()


def main() -> None:
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
