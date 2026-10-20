"""Globale Hotkeys über die Windows-API `RegisterHotKey`.

Robuster als ein Low-Level-Tastaturhook: Windows filtert Auto-Repeat selbst (MOD_NOREPEAT),
der Hotkey kann nicht stillschweigend wegen Timeouts entfernt werden, und eine bereits
von einem anderen Programm belegte Taste wird als Fehler gemeldet statt ignoriert.

Der Callback läuft im Hotkey-Thread – Tk-Widgets dort nicht anfassen.
"""

import sys
import threading
from typing import Callable

MOD_NOREPEAT = 0x4000
WM_HOTKEY = 0x0312
WM_QUIT = 0x0012
PM_NOREMOVE = 0x0000
VK_F1 = 0x70

_next_id = 1
_id_lock = threading.Lock()


class HotkeyError(RuntimeError):
    pass


def _vk_for(key: str) -> int:
    key = key.lower()
    if key.startswith("f") and key[1:].isdigit() and 1 <= int(key[1:]) <= 24:
        return VK_F1 + int(key[1:]) - 1
    raise ValueError(f"Nicht unterstützte Taste: {key!r} (erlaubt: f1–f24)")


class GlobalHotkey:
    def __init__(self, key: str, callback: Callable[[], None]):
        if sys.platform != "win32":
            raise HotkeyError("Globale Hotkeys werden nur unter Windows unterstützt")
        self.key = key.upper()
        self._vk = _vk_for(key)
        self._callback = callback
        self._thread: threading.Thread | None = None
        self._thread_id = 0
        self._ready = threading.Event()
        self._error: str | None = None
        global _next_id
        with _id_lock:
            self._id = _next_id
            _next_id += 1

    def start(self) -> None:
        self._ready.clear()
        self._error = None
        self._thread = threading.Thread(target=self._run, name="GlobalHotkey", daemon=True)
        self._thread.start()
        self._ready.wait(timeout=2)
        if self._error:
            self._thread.join(timeout=1)
            self._thread = None
            raise HotkeyError(self._error)

    def stop(self) -> None:
        if self._thread is None:
            return
        import ctypes
        ctypes.windll.user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)
        self._thread.join(timeout=1)
        self._thread = None

    def _run(self) -> None:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        user32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
        user32.GetMessageW.restype = wintypes.BOOL
        msg = wintypes.MSG()

        self._thread_id = ctypes.windll.kernel32.GetCurrentThreadId()
        # Nachrichtenschlange des Threads anlegen, damit PostThreadMessage aus stop() ankommt.
        user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, PM_NOREMOVE)
        if not user32.RegisterHotKey(None, self._id, MOD_NOREPEAT, self._vk):
            self._error = f"{self.key} ist schon von einem anderen Programm belegt"
            self._ready.set()
            return
        self._ready.set()
        try:
            while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                if msg.message == WM_HOTKEY and msg.wParam == self._id:
                    try:
                        self._callback()
                    except Exception:
                        import traceback
                        traceback.print_exc()
        finally:
            user32.UnregisterHotKey(None, self._id)
