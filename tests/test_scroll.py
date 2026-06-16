"""Tests for Timeline scroll lane detection and gestures."""

from __future__ import annotations

from maps_timeline.scroll import (
    expand_timeline_panel,
    swipe_timeline_content_down,
    swipe_timeline_content_up,
    timeline_scroll_lane,
)
from tests.conftest import RecordingSwipeDriver, button_xml, day_dump_xml, text_xml


def test_timeline_scroll_lane_uses_segment_column():
    """Anchor swipes in the horizontal center of parsed Timeline segments."""
    dump = day_dump_xml(
        button_xml(
            "C. 29 5450, Hora de salida: 1:49 PM, C. 29 5450, B1902 City Bell",
            bounds="[213,2058][1211,2261]",
        ),
        button_xml(
            "En automóvil, 26 min, 10 km, De 1:49 PM a 2:15 PM",
            bounds="[213,2313][1211,2561]",
        ),
    )
    x, y_start, y_end = timeline_scroll_lane(dump)
    assert 213 <= x <= 1211
    assert y_start >= 1900
    assert y_end <= 3000
    assert y_end > y_start
    assert y_end - y_start <= 400


def test_timeline_scroll_lane_defaults_when_no_segments():
    """Use a safe fallback lane when the dump has no Timeline segments yet."""
    dump = day_dump_xml(text_xml("Wed Jun 3, 2026"), text_xml("1 visitas"))
    x, y_start, y_end = timeline_scroll_lane(dump)
    assert x == 720
    assert y_start >= 1900
    assert y_end > y_start


def test_timeline_scroll_lane_skips_invalid_bounds():
    """Ignore segment buttons whose bounds cannot be parsed."""
    dump = day_dump_xml(
        button_xml(
            "En automóvil, 10 min, 2,4 km, De 4:49 PM a 4:59 PM",
            bounds="not-bounds",
        ),
        button_xml(
            "C. 29 5450, Hora de salida: 4:08 PM, C. 29 5450, B1902 City Bell",
            bounds="[213,2058][1211,2261]",
        ),
    )
    x, y_start, y_end = timeline_scroll_lane(dump)
    assert 213 <= x <= 1211
    assert y_end > y_start


def test_timeline_scroll_lane_clamps_segments_above_max_lane():
    """Keep swipes valid when segment bounds fall mostly above the lane chrome."""
    dump = day_dump_xml(
        button_xml(
            "Cafe, De 4:59 PM a 5:59 PM, Main 1",
            bounds="[213,3500][1211,3600]",
        )
    )
    x, y_start, y_end = timeline_scroll_lane(dump)
    assert 213 <= x <= 1211
    assert y_end > y_start


def test_swipe_timeline_content_gestures_use_lane():
    """Issue short swipes through the computed lane coordinates."""
    dump = day_dump_xml(
        button_xml(
            "Cafe, De 4:59 PM a 5:59 PM, Main 1",
            bounds="[213,2058][1211,2261]",
        )
    )
    driver = RecordingSwipeDriver()

    swipe_timeline_content_up(driver, dump)
    swipe_timeline_content_down(driver, dump)
    assert len(driver.swipes) == 2
    assert driver.swipes[0][1] < driver.swipes[0][3]
    assert driver.swipes[1][1] > driver.swipes[1][3]


def test_expand_timeline_panel_swipes_up_on_the_sheet():
    """Drag the bottom sheet upward from the header area."""
    dump = day_dump_xml(text_xml("Today", bounds="[0,1500][1440,1600]"))
    driver = RecordingSwipeDriver()

    expand_timeline_panel(driver, dump)
    assert len(driver.swipes) == 1
    x1, y1, x2, y2, duration_ms = driver.swipes[0]
    assert x1 == x2 == 720
    assert y1 > y2
    assert duration_ms == 550


def test_expand_timeline_panel_uses_fallback_without_header():
    """Use screen-based coordinates when the date header is not visible."""
    driver = RecordingSwipeDriver()

    expand_timeline_panel(driver, "<hierarchy/>")
    assert driver.swipes[0][1] > driver.swipes[0][3]
