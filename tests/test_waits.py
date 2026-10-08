"""Tests for explicit wait helpers."""

from __future__ import annotations

from maps_timeline.device import Driver
from maps_timeline.parser import count_timeline_segments
from maps_timeline.waits import (
    dump_full_timeline,
    ensure_timeline_panel_expanded,
    wait_for_stable_screen,
    wait_until,
)
from tests.conftest import MinimalDriver, button_xml, day_dump_xml, patch_instant_waits, text_xml


class _RevealDriver(MinimalDriver):
    """Show `before` until the first list swipe, then `after`; count the swipes."""

    def __init__(self, before: str, after: str) -> None:
        self.before = before
        self.after = after
        self.swipes = 0

    def dump(self) -> str:
        """Return what the list shows after the swipes so far."""
        return self.after if self.swipes else self.before

    def swipe(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        self, x1: int, y1: int, x2: int, y2: int, duration_ms: int = 300
    ) -> None:
        """Count one list swipe."""
        del x1, y1, x2, y2, duration_ms
        self.swipes += 1


def test_wait_for_stable_screen_returns_matching_dump():
    """Return immediately when two consecutive dumps are identical."""
    xml = "<hierarchy><node/></hierarchy>"
    calls = {"n": 0}

    def get_dump() -> str:
        calls["n"] += 1
        return xml

    result = wait_for_stable_screen(get_dump, settle=0.0, timeout=1.0)
    assert result == xml
    assert calls["n"] >= 2


def test_wait_for_stable_screen_timeout_returns_last_dump():
    """Return the last dump when stability is not reached before timeout."""
    values = ["<a/>", "<b/>", "<c/>"]
    idx = {"i": 0}

    def get_dump() -> str:
        value = values[min(idx["i"], len(values) - 1)]
        idx["i"] += 1
        return value

    result = wait_for_stable_screen(get_dump, settle=0.0, timeout=0.01)
    assert result in values


def test_wait_for_stable_screen_immediate_timeout_returns_first_dump(monkeypatch):
    """Return the first dump when the timeout budget is already exhausted."""
    monkeypatch.setattr("maps_timeline.waits.time.monotonic", lambda: 100.0)
    assert wait_for_stable_screen(lambda: "<only/>", settle=0.0, timeout=0.0) == "<only/>"


def test_wait_until_returns_true_when_predicate_succeeds():
    """Return True as soon as the predicate becomes true."""
    state = {"ready": False}

    def predicate() -> bool:
        state["ready"] = True
        return state["ready"]

    assert wait_until(predicate, timeout=1.0, poll=0.0) is True


def test_wait_until_returns_false_on_timeout():
    """Return False when the predicate never becomes true."""
    assert wait_until(lambda: False, timeout=0.01, poll=0.0) is False


def test_dump_full_timeline_scrolls_for_lazy_loaded_segments(monkeypatch):
    """Keep the dump with the most segments after scrolling the Timeline list."""
    short_xml = day_dump_xml(
        text_xml("Sun Jun 7, 2026"),
        button_xml("C. 12 3456, Hora de salida: 1:49 PM, C. 12 3456, B1900 Villa Ejemplo"),
        button_xml("En automóvil, 26 min, 10 km, De 1:49 PM a 2:15 PM"),
    )
    full_xml = day_dump_xml(
        text_xml("Sun Jun 7, 2026"),
        button_xml("C. 12 3456, Hora de salida: 1:49 PM, C. 12 3456, B1900 Villa Ejemplo"),
        button_xml("En automóvil, 26 min, 10 km, De 1:49 PM a 2:15 PM"),
        button_xml("C. 12 3456, Hora de llegada: 8:18 PM, C. 12 3456, B1900 Villa Ejemplo"),
    )

    patch_instant_waits(monkeypatch)
    driver = _RevealDriver(short_xml, full_xml)
    result = dump_full_timeline(driver)
    assert result == full_xml
    assert driver.swipes >= 1


def test_dump_full_timeline_scrolls_to_top_before_loading_bottom(monkeypatch):
    """Reset the list to the top before scrolling down for lazy-loaded segments."""
    calls: list[str] = []

    def fake_top(_driver: Driver, _dump: str, **kwargs: object) -> None:
        del kwargs
        calls.append("top")

    patch_instant_waits(monkeypatch, scroll_to_top=fake_top)
    counts = iter((0, 1))

    def fake_count(_dump: str) -> int:
        return next(counts, 1)

    monkeypatch.setattr("maps_timeline.waits.count_timeline_segments", fake_count)

    class NoSwipeDriver(MinimalDriver):
        """Minimal driver that only returns a stable dump."""

        def dump(self) -> str:
            """Return a minimal stable Timeline dump."""
            return day_dump_xml(
                text_xml("Sun Jun 7, 2026"),
                button_xml("C. 12 3456, Hora de salida: 1:49 PM, C. 12 3456, B1900 Villa Ejemplo"),
            )

    dump_full_timeline(NoSwipeDriver())
    assert calls == ["top"]


def test_dump_full_timeline_resets_scroll_after_day_change(monkeypatch):
    """Scroll toward the top before loading a new day that inherited list position."""
    calls: list[str] = []

    def fake_reset(_driver: Driver, _dump: str) -> None:
        calls.append("reset")

    monkeypatch.setattr("maps_timeline.waits._reset_timeline_scroll_after_day_change", fake_reset)
    patch_instant_waits(monkeypatch)

    class StableDriver(MinimalDriver):
        """Minimal driver that only returns a stable dump."""

        def dump(self) -> str:
            """Return a minimal stable Timeline dump."""
            return day_dump_xml(
                text_xml("Yesterday"),
                button_xml("C. 12 3456, Hora de salida: 1:49 PM, C. 12 3456, B1900 Villa Ejemplo"),
            )

    dump_full_timeline(StableDriver(), reset_scroll=True)
    assert calls == ["reset"]


def test_ensure_timeline_panel_expanded_swipes_until_ready(monkeypatch):
    """Keep expanding the sheet until the header moves to the top region."""
    collapsed = day_dump_xml(
        text_xml("Today", bounds="[0,1500][1440,1600]"),
        text_xml("1 visitas", bounds="[0,1600][1440,1700]"),
        button_xml("C. 1, Hora de salida: 4:08 PM, C. 1, City", bounds="[0,1800][1440,2000]"),
    )
    expanded = day_dump_xml(
        text_xml("Today", bounds="[0,200][1440,300]"),
        text_xml("1 visitas", bounds="[0,300][1440,400]"),
        button_xml("C. 1, Hora de salida: 4:08 PM, C. 1, City", bounds="[0,500][1440,700]"),
    )

    class PanelDriver(MinimalDriver):
        """Return the collapsed dump first, then the expanded dump."""

        def __init__(self) -> None:
            self.reads = 0
            self.swipes: list[tuple[int, int, int, int, int]] = []

        def dump(self) -> str:
            """Return the collapsed dump twice, then the expanded dump."""
            self.reads += 1
            return collapsed if self.reads <= 2 else expanded

        def swipe(  # pylint: disable=too-many-arguments,too-many-positional-arguments
            self, x1: int, y1: int, x2: int, y2: int, duration_ms: int = 300
        ) -> None:
            """Record one panel expansion swipe."""
            self.swipes.append((x1, y1, x2, y2, duration_ms))

    patch_instant_waits(monkeypatch)
    driver = PanelDriver()
    result = ensure_timeline_panel_expanded(driver)
    assert result == expanded
    assert driver.swipes


def test_dump_full_timeline_skips_scroll_on_unrecognized_screen(monkeypatch):
    """Do not swipe when the dump is not the Timeline day view."""

    class BareDriver(MinimalDriver):
        """Return an empty hierarchy dump and record swipe attempts."""

        def __init__(self) -> None:
            self.swipes: list[tuple[int, int, int, int]] = []

        def swipe(  # pylint: disable=too-many-arguments,too-many-positional-arguments
            self, x1: int, y1: int, x2: int, y2: int, duration_ms: int = 300
        ) -> None:
            """Record one swipe attempt."""
            del duration_ms
            self.swipes.append((x1, y1, x2, y2))

    patch_instant_waits(monkeypatch)
    driver = BareDriver()
    dump_full_timeline(driver)
    assert not driver.swipes


def test_dump_full_timeline_respects_max_scroll_attempts(monkeypatch):
    """Stop scrolling after the configured attempt limit even if segments keep growing."""
    xml = day_dump_xml(
        text_xml("Sun Jun 7, 2026"),
        button_xml("C. 12 3456, Hora de salida: 1:49 PM, C. 12 3456, B1900 Villa Ejemplo"),
    )

    class GrowingDriver(MinimalDriver):
        """Increase the segment count on every dump after a swipe."""

        def __init__(self) -> None:
            self.swipes = 0
            self.segments = 1

        def dump(self) -> str:
            """Return a dump whose segment count grows after each swipe."""
            buttons = [
                button_xml("C. 12 3456, Hora de salida: 1:49 PM, C. 12 3456, B1900 Villa Ejemplo")
            ]
            if self.swipes:
                buttons.extend(
                    button_xml(
                        f"Place {i}, De 1:00 PM a 2:00 PM, Street {i}, City",
                    )
                    for i in range(1, self.segments + 1)
                )
            return day_dump_xml(text_xml("Sun Jun 7, 2026"), *buttons)

        def swipe(  # pylint: disable=too-many-arguments,too-many-positional-arguments
            self, x1: int, y1: int, x2: int, y2: int, duration_ms: int = 300
        ) -> None:
            """Increase swipe and segment counters."""
            del x1, y1, x2, y2, duration_ms
            self.swipes += 1
            self.segments += 1

    monkeypatch.setattr("maps_timeline.waits._MAX_TIMELINE_SCROLLS", 2)
    patch_instant_waits(monkeypatch)
    driver = GrowingDriver()
    result = dump_full_timeline(driver)
    assert driver.swipes == 2
    assert count_timeline_segments(result) > count_timeline_segments(xml)


def test_dump_full_timeline_keeps_scrolling_for_return_home(monkeypatch):
    """Keep scrolling when the day starts at home but the arrival card is still missing."""
    without_arrival = day_dump_xml(
        text_xml("Sat Jun 6, 2026"),
        button_xml("C. 12 3456, Hora de salida: 4:08 PM, C. 12 3456, B1900 Villa Ejemplo"),
        button_xml("En automóvil, 42 min, 13 km, De 8:55 PM a 9:38 PM"),
        button_xml("Cafe Ejemplo, De 4:59 PM a 6:36 PM, Centro, C. 7 120, B1900 Villa Ejemplo"),
    )
    with_arrival = day_dump_xml(
        text_xml("Sat Jun 6, 2026"),
        button_xml("En automóvil, 42 min, 13 km, De 8:55 PM a 9:38 PM"),
        button_xml("Cafe Ejemplo, De 4:59 PM a 6:36 PM, Centro, C. 7 120, B1900 Villa Ejemplo"),
        button_xml("C. 12 3456, Hora de llegada: 9:38 PM, C. 12 3456, B1900 Villa Ejemplo"),
    )

    patch_instant_waits(monkeypatch)
    driver = _RevealDriver(without_arrival, with_arrival)
    result = dump_full_timeline(driver)
    assert result == with_arrival
    assert driver.swipes >= 1
