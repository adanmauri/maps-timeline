"""Shared fixtures and helpers for the test suite."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import pytest

from maps_timeline import paths


def button_xml(desc: str, *, clickable: bool = False, bounds: str = "[0,0][100,100]") -> str:
    """Build a Button node fragment for synthetic UI dumps."""
    click = ' clickable="true"' if clickable else ""
    return (
        f'<node class="android.widget.Button" content-desc="{desc}" ' f'bounds="{bounds}"{click}/>'
    )


def text_xml(value: str, *, bounds: str = "[0,0][1,1]") -> str:
    """Build a TextView node fragment for synthetic UI dumps."""
    return f'<node class="android.widget.TextView" text="{value}" bounds="{bounds}"/>'


def day_dump_xml(*parts: str) -> str:
    """Wrap node fragments in a minimal hierarchy root."""
    return "<hierarchy>" + "".join(parts) + "</hierarchy>"


class MinimalDriver:
    """No-op Driver for tests that override only the methods they exercise."""

    def dump(self) -> str:
        """Return an empty hierarchy dump."""
        return "<hierarchy/>"

    def tap_xy(self, x: int, y: int) -> None:
        """Ignore tap calls."""
        del x, y

    def swipe(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        self, x1: int, y1: int, x2: int, y2: int, duration_ms: int = 300
    ) -> None:
        """Ignore swipe calls."""
        del x1, y1, x2, y2, duration_ms

    def screenshot(self, path: str) -> None:
        """Ignore screenshot calls."""
        del path

    def is_healthy(self) -> bool:
        """Report that the fake driver is connected."""
        return True


class RecordingSwipeDriver(MinimalDriver):
    """Driver stub that records swipe gestures for scroll and panel tests."""

    def __init__(self) -> None:
        """Initialize an empty swipe log."""
        self.swipes: list[tuple[int, int, int, int, int]] = []

    def swipe(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        self, x1: int, y1: int, x2: int, y2: int, duration_ms: int = 300
    ) -> None:
        """Append one swipe to the test log."""
        self.swipes.append((x1, y1, x2, y2, duration_ms))


@dataclass
class FakeDriver:
    """In-memory Driver for pipeline and navigator tests."""

    dumps: list[str] = field(default_factory=list)
    taps: list[tuple[int, int]] = field(default_factory=list)
    screenshots: list[str] = field(default_factory=list)
    healthy: bool = True
    _dump_index: int = 0
    tap_previous: bool = True

    def dump(self) -> str:
        """Return the next XML dump (repeats the last one when the list ends)."""
        if not self.dumps:
            return "<hierarchy/>"
        idx = min(self._dump_index, len(self.dumps) - 1)
        self._dump_index += 1
        return self.dumps[idx]

    def tap_xy(self, x: int, y: int) -> None:
        """Record a tap coordinate."""
        self.taps.append((x, y))

    def swipe(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        self, x1: int, y1: int, x2: int, y2: int, duration_ms: int = 300
    ) -> None:
        """No-op swipe for tests."""

    def screenshot(self, path: str) -> None:
        """Record a screenshot path."""
        self.screenshots.append(path)

    def is_healthy(self) -> bool:
        """Return the configured health flag."""
        return self.healthy


@pytest.fixture
def isolated_paths(tmp_path: Path, monkeypatch):
    """Point run storage and the latest marker at a temporary directory."""
    runs_root = tmp_path / "runs"
    marker = tmp_path / "latest"
    monkeypatch.setattr(paths, "RUNS_DIR", runs_root)
    monkeypatch.setattr(paths, "LATEST_MARKER", marker)
    return runs_root, marker


def patch_instant_waits(
    monkeypatch,
    *,
    reset_after_day_change: bool = False,
    scroll_to_top=None,
    stable_screen_fn=None,
) -> None:
    """Stub sleeps and stable-screen waits for fast offline tests."""
    monkeypatch.setattr("maps_timeline.waits.time.sleep", lambda _: None)
    if scroll_to_top is None:
        monkeypatch.setattr(
            "maps_timeline.waits._scroll_timeline_to_top", lambda *_args, **_kwargs: None
        )
    else:
        monkeypatch.setattr("maps_timeline.waits._scroll_timeline_to_top", scroll_to_top)
    if reset_after_day_change:
        monkeypatch.setattr(
            "maps_timeline.waits._reset_timeline_scroll_after_day_change", lambda *_args: None
        )
    if stable_screen_fn is None:

        def _instant_stable_screen(get_dump, settle=0.6, timeout=12.0):
            """Return the current dump without waiting."""
            del settle, timeout
            return get_dump()

        stable_screen_fn = _instant_stable_screen

    monkeypatch.setattr("maps_timeline.waits.wait_for_stable_screen", stable_screen_fn)


@pytest.fixture
def sample_jsonl(tmp_path: Path) -> Path:
    """Write a minimal raw JSONL file and return its path."""
    payload = (
        '{"day":"2026-06-06","segments":[{"type":"place_visit","title":"Cafe",'
        '"address":"Main 1","start_time":"4:59 PM","end_time":"5:59 PM",'
        '"duration_text":"10 min","distance_text":"2,4 km","confirmed":true,'
        '"needs_user_action":false}]}\n'
    )
    path = tmp_path / "timeline.jsonl"
    path.write_text(payload, encoding="utf-8")
    return path


@pytest.fixture
def timeline_day() -> date:
    """Reference date used across navigation tests."""
    return date(2026, 6, 10)
