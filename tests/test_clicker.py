import time

import pytest

from tools.autoclicker import ClickConfig, Clicker


class FakeMouse:
    def __init__(self):
        self.position = (0, 0)
        self.clicks = []

    def click(self, button, count=1):
        self.clicks.append((button, count, self.position))


BUTTONS = {"left": "L", "right": "R", "middle": "M"}


def wait_until_stopped(clicker, timeout=2.0):
    end = time.monotonic() + timeout
    while clicker.running and time.monotonic() < end:
        time.sleep(0.01)
    assert not clicker.running


def test_repeat_count_is_respected():
    mouse = FakeMouse()
    clicker = Clicker(mouse, BUTTONS)
    clicker.start(ClickConfig(interval_ms=1, repeat=5))
    wait_until_stopped(clicker)
    assert len(mouse.clicks) == 5
    assert clicker.clicks == 5


def test_button_double_click_and_fixed_position():
    mouse = FakeMouse()
    clicker = Clicker(mouse, BUTTONS)
    clicker.start(ClickConfig(interval_ms=1, button="right", double=True, repeat=2, position=(40, 50)))
    wait_until_stopped(clicker)
    assert mouse.clicks == [("R", 2, (40, 50)), ("R", 2, (40, 50))]


def test_infinite_until_stopped():
    mouse = FakeMouse()
    clicker = Clicker(mouse, BUTTONS)
    clicker.start(ClickConfig(interval_ms=1, repeat=0))
    time.sleep(0.05)
    assert clicker.running
    clicker.stop()
    assert not clicker.running
    count = len(mouse.clicks)
    assert count > 0
    time.sleep(0.03)
    assert len(mouse.clicks) == count


def test_stop_interrupts_long_interval_immediately():
    clicker = Clicker(FakeMouse(), BUTTONS)
    clicker.start(ClickConfig(interval_ms=60_000))
    time.sleep(0.02)
    t = time.monotonic()
    clicker.stop()
    assert time.monotonic() - t < 0.5


def test_restart_resets_counter():
    clicker = Clicker(FakeMouse(), BUTTONS)
    clicker.start(ClickConfig(interval_ms=1, repeat=3))
    wait_until_stopped(clicker)
    clicker.start(ClickConfig(interval_ms=1, repeat=2))
    wait_until_stopped(clicker)
    assert clicker.clicks == 2


def test_skips_clicks_while_blocked_but_keeps_running():
    mouse = FakeMouse()
    mouse.position = (5, 5)
    blocked = {"on": True}
    clicker = Clicker(mouse, BUTTONS, is_blocked=lambda pos: blocked["on"])
    clicker.start(ClickConfig(interval_ms=1, repeat=3))
    time.sleep(0.05)
    assert clicker.running
    assert clicker.waiting
    assert mouse.clicks == []
    blocked["on"] = False
    wait_until_stopped(clicker)
    assert len(mouse.clicks) == 3
    assert not clicker.waiting


def test_blocked_check_uses_fixed_position():
    mouse = FakeMouse()
    seen = []
    clicker = Clicker(mouse, BUTTONS, is_blocked=lambda pos: seen.append(pos) or False)
    clicker.start(ClickConfig(interval_ms=1, repeat=1, position=(7, 8)))
    wait_until_stopped(clicker)
    assert seen == [(7, 8)]


@pytest.mark.parametrize("kwargs", [{"interval_ms": 0}, {"repeat": -1}, {"button": "foo"}])
def test_invalid_config_rejected(kwargs):
    with pytest.raises(ValueError):
        ClickConfig(**kwargs)
