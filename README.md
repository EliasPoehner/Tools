# werkbank

Sammlung kleiner Alltags-Tools in einem Launcher (Python + tkinter).

**Starten:** `start.bat` doppelklicken (legt beim ersten Mal `.venv` an).
**Tests:** `.venv\Scripts\python -m pytest`

## Tools

| Tool | Was es macht |
|---|---|
| Autoklicker | Klickt im Intervall (Taste, Doppelklick, Anzahl, fester Punkt). **F6** startet/stoppt global. Klickt nie ins eigene Fenster – solange die Maus darüber ist, wartet er. |
| Speicher | Speicher-Explorer: Treemap zeigt grafisch, welche Ordner/Dateien wie viel Platz belegen. Klick auf Kachel öffnet den Ordner, „↑ Hoch“ geht zurück, „Im Explorer“ öffnet ihn in Windows. Dateien < 1 MB werden pro Ordner zusammengefasst. |

## Neues Tool hinzufügen

Eine Datei in `tools/` anlegen – sie erscheint automatisch in der Sidebar:

```python
from tkinter import ttk
from core.registry import Tool

class MeinTool(Tool):
    name = "Mein Tool"
    description = "Kurz, was es tut."

    def build(self, parent: ttk.Frame) -> None:
        ttk.Label(parent, text="Hallo").pack()

    def on_close(self) -> None:
        pass  # Threads/Listener stoppen
```

- Styles/Farben aus `core/theme.py` nutzen (`Accent.TButton`, `Muted.TLabel`, …).
- Globale Tastenkürzel: `core.hotkey.GlobalHotkey("f7", callback)` – Callback läuft im Hotkey-Thread.
- Arbeit in Threads: Tk-Widgets nur im Main-Thread anfassen (per `after()`-Polling, siehe Autoklicker).
- Logik von der UI trennen, damit sie ohne Fenster testbar ist (`tests/`).
- Neue Abhängigkeiten in `requirements.txt` eintragen.
