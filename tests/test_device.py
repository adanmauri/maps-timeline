"""Tests for the device transport layer."""

from __future__ import annotations

import subprocess
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from maps_timeline.device import AdbRawDriver, U2Driver, make_driver


def test_u2_driver_roundtrip(monkeypatch):
    """Exercise U2Driver methods against a mocked uiautomator2 session."""
    device = MagicMock()
    device.dump_hierarchy.return_value = "<hierarchy/>"
    device.info = {"display": True}

    fake_u2 = MagicMock()
    fake_u2.connect.return_value = device
    monkeypatch.setitem(__import__("sys").modules, "uiautomator2", fake_u2)

    driver = U2Driver(serial="abc")
    assert driver.dump() == "<hierarchy/>"
    driver.tap_xy(1, 2)
    driver.swipe(0, 0, 1, 1, duration_ms=500)
    driver.screenshot("/tmp/x.png")
    assert driver.is_healthy() is True
    device.click.assert_called_once_with(1, 2)


def test_u2_driver_connect_without_serial(monkeypatch):
    """Call uiautomator2.connect() with no serial when none is given."""
    fake_u2 = MagicMock()
    fake_u2.connect.return_value = MagicMock(info={})
    monkeypatch.setitem(__import__("sys").modules, "uiautomator2", fake_u2)

    U2Driver()
    fake_u2.connect.assert_called_once_with()


def test_u2_driver_is_healthy_on_error(monkeypatch):
    """Return False when the uiautomator2 session raises."""

    class BadSession:
        """uiautomator2 session stub that fails on info access."""

        @property
        def info(self) -> dict:
            """Raise to simulate a dead uiautomator2 session."""
            raise OSError("down")

        def service(self, _name: str) -> None:
            """No-op service accessor for test parity."""
            return None

    fake_u2 = MagicMock()
    fake_u2.connect.return_value = BadSession()
    monkeypatch.setitem(__import__("sys").modules, "uiautomator2", fake_u2)

    driver = U2Driver()
    assert driver.is_healthy() is False


def test_adb_raw_driver_roundtrip(tmp_path, monkeypatch):
    """Exercise AdbRawDriver methods with mocked subprocess calls."""
    png = b"\x89PNG"
    completed = SimpleNamespace(stdout=png, returncode=0)

    def fake_run(cmd, **kwargs):
        if kwargs.get("capture_output"):
            if "screencap" in cmd:
                return completed
            return SimpleNamespace(stdout="device\n", returncode=0)
        return SimpleNamespace(stdout="", returncode=0)

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr("maps_timeline.device.shutil.which", lambda _: "/usr/bin/adb")

    driver = AdbRawDriver(serial="serial-1")
    assert driver.dump() == "device\n"
    driver.tap_xy(3, 4)
    driver.swipe(0, 0, 1, 1, duration_ms=100)
    out = tmp_path / "shot.png"
    driver.screenshot(str(out))
    assert out.read_bytes() == png
    assert driver.is_healthy() is True


def test_adb_raw_driver_unhealthy_without_adb(monkeypatch):
    """Return False when adb is not on PATH."""
    monkeypatch.setattr("maps_timeline.device.shutil.which", lambda _: None)
    assert AdbRawDriver().is_healthy() is False


def test_adb_raw_driver_unhealthy_on_subprocess_error(monkeypatch):
    """Return False when adb get-state fails."""
    monkeypatch.setattr("maps_timeline.device.shutil.which", lambda _: "/usr/bin/adb")
    monkeypatch.setattr(
        subprocess,
        "run",
        MagicMock(side_effect=subprocess.CalledProcessError(1, "adb")),
    )
    assert AdbRawDriver().is_healthy() is False


def test_make_driver_prefers_healthy_u2(monkeypatch):
    """Return U2Driver when uiautomator2 connects and is healthy."""
    monkeypatch.setattr(
        "maps_timeline.device.U2Driver",
        lambda serial=None: SimpleNamespace(is_healthy=lambda: True),
    )
    driver = make_driver(prefer="u2")
    assert driver.is_healthy() is True


def test_make_driver_falls_back_to_adb(monkeypatch):
    """Fall back to AdbRawDriver when uiautomator2 is unavailable."""
    monkeypatch.setattr(
        "maps_timeline.device.U2Driver",
        MagicMock(side_effect=ImportError("no u2")),
    )
    monkeypatch.setattr(
        "maps_timeline.device.AdbRawDriver",
        lambda serial=None: SimpleNamespace(is_healthy=lambda: True),
    )
    driver = make_driver(prefer="u2")
    assert driver.is_healthy() is True


def test_make_driver_u2_unhealthy_falls_back_to_adb(monkeypatch):
    """Fall back to adb when uiautomator2 connects but is not healthy."""
    monkeypatch.setattr(
        "maps_timeline.device.U2Driver",
        lambda serial=None: SimpleNamespace(is_healthy=lambda: False),
    )
    monkeypatch.setattr(
        "maps_timeline.device.AdbRawDriver",
        lambda serial=None: SimpleNamespace(is_healthy=lambda: True),
    )
    assert make_driver(prefer="u2").is_healthy() is True


def test_make_driver_raises_when_nothing_connects(monkeypatch):
    """Raise RuntimeError when no driver can connect."""
    monkeypatch.setattr(
        "maps_timeline.device.U2Driver",
        MagicMock(side_effect=RuntimeError("u2 down")),
    )
    monkeypatch.setattr(
        "maps_timeline.device.AdbRawDriver",
        lambda serial=None: SimpleNamespace(is_healthy=lambda: False),
    )
    with pytest.raises(RuntimeError, match="Could not connect"):
        make_driver(prefer="adb")
