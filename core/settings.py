"""Einstellungen dauerhaft speichern: eine JSON-Datei im Benutzerprofil, ein Abschnitt pro Tool."""

import json
import os
from pathlib import Path


def config_dir() -> Path:
    base = os.environ.get("APPDATA") or os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "werkbank"


class Settings:
    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path is not None else config_dir() / "settings.json"
        self.data = self._load()

    def _load(self) -> dict:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return data if isinstance(data, dict) else {}

    def section(self, name: str) -> dict:
        """Veränderbares Dict für einen Bereich (z. B. ein Tool); landet beim `save()` in der Datei."""
        sec = self.data.get(name)
        if not isinstance(sec, dict):
            sec = self.data[name] = {}
        return sec

    def save(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.data, indent=2, ensure_ascii=False), encoding="utf-8")
            os.replace(tmp, self.path)  # atomar: bei Absturz bleibt die alte Datei heil
        except (OSError, TypeError, ValueError) as e:
            print(f"[werkbank] Einstellungen konnten nicht gespeichert werden: {e}")
