# werkbank

Sammlung kleiner Alltags-Tools in einem Launcher (Python + tkinter).

**Starten:** `start.bat` doppelklicken (legt beim ersten Mal `.venv` an und installiert neu, wenn sich `requirements.txt` ändert).
**Wechseln:** Strg+1 … Strg+9 öffnet das n-te Tool.
**Einstellungen & Log:** `%APPDATA%\werkbank\` (`settings.json`, `werkbank.log`) – Fenstergröße, letztes Tool und Tool-Werte werden gemerkt.
**Tests:** `.venv\Scripts\python -m pytest`
**Als .exe:** `build.bat` doppelklicken → `dist\werkbank.exe` (eine Datei, kein Python nötig). Fertige Builds gibt es auch unter GitHub → Actions → „build“ → Artefakt `werkbank-exe`.

## Tools

| Tool | Was es macht |
|---|---|
| Autoklicker | Klickt im Intervall (Taste, Doppelklick, Anzahl, fester Punkt). **F6** startet/stoppt global. Klickt nie ins eigene Fenster – solange es unter der Maus sichtbar ist, wartet er (liegt es verdeckt im Hintergrund, wird normal geklickt). |
| Speicher | Speicher-Explorer: Treemap zeigt grafisch, welche Ordner/Dateien wie viel Platz belegen. Klick auf Kachel öffnet den Ordner, „↑ Hoch“ geht zurück, „Im Explorer“ öffnet ihn in Windows. Rechtsklick/Backspace = zurück, Doppelklick auf Datei = im Explorer zeigen, „↻ Aktualisieren“ scannt nur den aktuellen Ordner neu. Dateien < 1 MB werden pro Ordner zusammengefasst, reine Cloud-Platzhalter (OneDrive) zählen als 0. |

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

- `self.settings` ist ein Dict, das zwischen Starts erhalten bleibt (in `build()` lesen, in `on_close()` schreiben; nur JSON-Typen).
- Alle Tools werden beim Start gebaut (damit z. B. Hotkeys sofort gelten) – `build()` also schlank halten.
- Fehler in `build()` oder Tk-Callbacks landen im Log und werden angezeigt, statt den Launcher zu blockieren.

- Styles/Farben aus `core/theme.py` nutzen (`Accent.TButton`, `Muted.TLabel`, …).
- Globale Tastenkürzel: `core.hotkey.GlobalHotkey("f7", callback)` – Callback läuft im Hotkey-Thread.
- Arbeit in Threads: Tk-Widgets nur im Main-Thread anfassen (per `after()`-Polling, siehe Autoklicker).
- Logik von der UI trennen, damit sie ohne Fenster testbar ist (`tests/`).
- Neue Abhängigkeiten in `requirements.txt` eintragen.
