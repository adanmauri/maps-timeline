"""Transport layer to the device.

The driver is deliberately "dumb": it only knows how to dump the XML hierarchy,
tap coordinates, swipe, and take screenshots. All the intelligence for finding
nodes lives in `parser.py` / `navigator.py`, operating on the XML. This keeps the
uiautomator2-based driver and the raw-ADB one interchangeable and testable with
the same dumps.

Driver selection: chosen at startup based on availability (uiautomator2 if it
connects, raw ADB as a fallback).
"""

from __future__ import annotations

import shutil
import subprocess  # nosec B404
from typing import Protocol, runtime_checkable


@runtime_checkable
class Driver(Protocol):
    """Minimal device transport interface shared by all driver implementations."""

    def dump(self) -> str:
        """Return the current screen hierarchy as a uiautomator XML string."""
        ...  # pylint: disable=unnecessary-ellipsis

    def tap_xy(self, x: int, y: int) -> None:
        """Tap the screen at the given coordinates."""
        ...  # pylint: disable=unnecessary-ellipsis

    def swipe(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        self, x1: int, y1: int, x2: int, y2: int, duration_ms: int = 300
    ) -> None:
        """Swipe from (x1, y1) to (x2, y2) over `duration_ms` milliseconds."""
        ...  # pylint: disable=unnecessary-ellipsis

    def screenshot(self, path: str) -> None:
        """Save a PNG screenshot of the current screen to `path`."""
        ...  # pylint: disable=unnecessary-ellipsis

    def is_healthy(self) -> bool:
        """Return True when the device connection is usable."""
        ...  # pylint: disable=unnecessary-ellipsis


class U2Driver:
    """Driver based on uiautomator2 (fast, dump via API)."""

    def __init__(self, serial: str | None = None):
        """Connect to the device via uiautomator2."""
        import uiautomator2 as u2  # pylint: disable=import-outside-toplevel

        self.d = u2.connect() if serial is None else u2.connect(serial)

    def dump(self) -> str:
        """Return the current screen hierarchy as XML."""
        return self.d.dump_hierarchy()

    def tap_xy(self, x: int, y: int) -> None:
        """Tap the screen at the given coordinates."""
        self.d.click(x, y)

    def swipe(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        self, x1: int, y1: int, x2: int, y2: int, duration_ms: int = 300
    ) -> None:
        """Swipe from (x1, y1) to (x2, y2) over `duration_ms` milliseconds."""
        self.d.swipe(x1, y1, x2, y2, duration=duration_ms / 1000)

    def screenshot(self, path: str) -> None:
        """Save a PNG screenshot of the current screen to `path`."""
        self.d.screenshot(path)

    def is_healthy(self) -> bool:
        """Return True when the uiautomator2 session responds."""
        try:
            return bool(self.d.info)
        except (OSError, RuntimeError, AttributeError):
            return False


class AdbRawDriver:
    """Fallback driver using raw `adb` commands."""

    def __init__(self, serial: str | None = None):
        """Build the adb argv prefix, optionally scoped to one device serial."""
        self._base = ["adb"] + (["-s", serial] if serial else [])

    def _run(self, *args: str, capture: bool = False) -> str:
        """Run an adb subcommand and return stdout when `capture` is True."""
        result = subprocess.run(  # nosec B603
            [*self._base, *args],
            check=True,
            capture_output=True,
            text=True,
        )
        return result.stdout if capture else ""

    def dump(self) -> str:
        """Return the current screen hierarchy as XML via raw adb."""
        self._run("shell", "uiautomator", "dump", "/sdcard/_gmt_dump.xml")
        return self._run("exec-out", "cat", "/sdcard/_gmt_dump.xml", capture=True)

    def tap_xy(self, x: int, y: int) -> None:
        """Tap the screen at the given coordinates."""
        self._run("shell", "input", "tap", str(x), str(y))

    def swipe(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        self, x1: int, y1: int, x2: int, y2: int, duration_ms: int = 300
    ) -> None:
        """Swipe from (x1, y1) to (x2, y2) over `duration_ms` milliseconds."""
        self._run(
            "shell",
            "input",
            "swipe",
            str(x1),
            str(y1),
            str(x2),
            str(y2),
            str(duration_ms),
        )

    def screenshot(self, path: str) -> None:
        """Save a PNG screenshot of the current screen to `path`."""
        out = subprocess.run(  # nosec B603
            [*self._base, "exec-out", "screencap", "-p"],
            check=True,
            capture_output=True,
        )
        with open(path, "wb") as fh:
            fh.write(out.stdout)

    def is_healthy(self) -> bool:
        """Return True when adb reports the device state as 'device'."""
        if shutil.which("adb") is None:
            return False
        try:
            out = self._run("get-state", capture=True)
            return out.strip() == "device"
        except subprocess.CalledProcessError:
            return False


def make_driver(serial: str | None = None, prefer: str = "u2") -> Driver:
    """Create the best available driver. `prefer` can be 'u2' or 'adb'."""
    if prefer == "u2":
        try:
            driver = U2Driver(serial)
            if driver.is_healthy():
                return driver
        except (ImportError, OSError, RuntimeError, AttributeError):
            pass
    adb = AdbRawDriver(serial)
    if not adb.is_healthy():
        raise RuntimeError(
            "Could not connect to the device. Check `adb devices` and USB debugging."
        )
    return adb
