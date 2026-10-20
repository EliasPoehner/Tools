"""Integrationstests mit echten (injizierten) Tastendrücken – nur Windows."""

import sys
import threading
import time

import pytest

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows-API")

from core.hotkey import GlobalHotkey, HotkeyError  # noqa: E402

# F13 gibt es auf normalen Tastaturen nicht -> kollidiert nicht mit echten Eingaben/Programmen.
KEY = "f13"


@pytest.fixture
def kb():
    from pynput import keyboard
    return keyboard.Controller(), keyboard.Key.f13


def wait_for(cond, timeout=1.0):
    end = time.monotonic() + timeout
    while not cond() and time.monotonic() < end:
        time.sleep(0.01)


def test_each_tap_fires_once(kb):
    controller, key = kb
    hits = []
    hk = GlobalHotkey(KEY, lambda: hits.append(1))
    hk.start()
    try:
        for _ in range(5):
            controller.tap(key)
            time.sleep(0.03)
        wait_for(lambda: len(hits) >= 5)
        time.sleep(0.1)
        assert len(hits) == 5
    finally:
        hk.stop()


def test_holding_key_fires_once(kb):
    controller, key = kb
    hits = []
    hk = GlobalHotkey(KEY, lambda: hits.append(1))
    hk.start()
    try:
        for _ in range(6):  # Auto-Repeat simulieren
            controller.press(key)
            time.sleep(0.03)
        controller.release(key)
        time.sleep(0.2)
        assert len(hits) == 1
    finally:
        hk.stop()


def test_stop_releases_key_for_reuse():
    hk = GlobalHotkey(KEY, lambda: None)
    hk.start()
    hk.stop()
    again = GlobalHotkey(KEY, lambda: None)
    again.start()
    again.stop()


def test_already_taken_raises():
    first = GlobalHotkey(KEY, lambda: None)
    first.start()
    try:
        with pytest.raises(HotkeyError):
            GlobalHotkey(KEY, lambda: None).start()
    finally:
        first.stop()


def test_stop_does_not_hang():
    hk = GlobalHotkey(KEY, lambda: None)
    hk.start()
    t = time.monotonic()
    hk.stop()
    assert time.monotonic() - t < 0.5
    assert not any(th.name == "GlobalHotkey" and th.is_alive() for th in threading.enumerate())
