"""Tool-Basisklasse und automatische Erkennung aller Tools im Ordner `tools/`."""

import importlib
import pkgutil
import traceback
from tkinter import ttk


class Tool:
    """Basisklasse für ein Tool. Neue Tools: Datei in `tools/` anlegen, von Tool erben, fertig."""

    name = "Unbenannt"
    description = ""

    def __init__(self) -> None:
        # Vom Launcher vor `build()` gesetzt; Inhalt wird beim Beenden gespeichert (nur JSON-Typen).
        self.settings: dict = {}

    def build(self, parent: ttk.Frame) -> None:
        """Baut die Oberfläche des Tools in `parent`. Wird einmal beim ersten Öffnen aufgerufen."""
        raise NotImplementedError

    def on_close(self) -> None:
        """Aufräumen beim Beenden des Launchers (Threads stoppen, Listener lösen, `self.settings` füllen, ...)."""


def discover_tools() -> list[type[Tool]]:
    import tools as package

    found: list[type[Tool]] = []
    for info in pkgutil.iter_modules(package.__path__):
        if info.name.startswith("_"):
            continue
        try:
            module = importlib.import_module(f"{package.__name__}.{info.name}")
        except Exception:
            print(f"[werkbank] Tool '{info.name}' konnte nicht geladen werden:")
            traceback.print_exc()
            continue
        for obj in vars(module).values():
            if (
                isinstance(obj, type)
                and issubclass(obj, Tool)
                and obj is not Tool
                and obj.__module__ == module.__name__
            ):
                found.append(obj)
    return sorted(found, key=lambda t: t.name.lower())
