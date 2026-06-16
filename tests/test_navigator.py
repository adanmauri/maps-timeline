"""Tests for Timeline navigation helpers."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from datetime import date

import pytest

from maps_timeline.navigator import Navigator, center_of, resolve_header_date
from tests.conftest import FakeDriver, button_xml, day_dump_xml, text_xml


def test_center_of_computes_midpoint():
    """Compute the center point from uiautomator bounds."""
    assert center_of("[0,0][10,20]") == (5, 10)


def test_center_of_rejects_invalid_bounds():
    """Raise ValueError for malformed bounds strings."""
    with pytest.raises(ValueError, match="Unexpected bounds"):
        center_of("not-bounds")


def test_resolve_header_date_absolute_month():
    """Parse an absolute English header date."""
    today = date(2026, 6, 10)
    assert resolve_header_date("Sat Jun 6, 2026", today) == date(2026, 6, 6)


def test_resolve_header_date_unknown_month():
    """Return None when the month abbreviation is not recognized."""
    assert resolve_header_date("Sat Zzz 6, 2026", date(2026, 6, 10)) is None


def test_navigator_header_text_delegates_to_parser(timeline_day: date):
    """Read the header text through the parser helper."""
    root = ET.fromstring(day_dump_xml(text_xml("Today")))
    nav = Navigator(FakeDriver(), timeline_day)
    assert nav.header_text(root) == "Today"


def test_navigator_displayed_date_without_header(timeline_day: date):
    """Return None when the dump has no recognizable header."""
    root = ET.fromstring(day_dump_xml())
    nav = Navigator(FakeDriver(), timeline_day)
    assert nav.displayed_date(root) is None


def test_navigator_tap_previous_day_success(timeline_day: date):
    """Tap the previous-day button when it is present and clickable."""
    xml = day_dump_xml(
        text_xml("Today"),
        button_xml("Día anterior", clickable=True, bounds="[0,0][10,10]"),
    )
    driver = FakeDriver()
    nav = Navigator(driver, timeline_day)
    root = ET.fromstring(xml)
    assert nav.tap_previous_day(root) is True
    assert driver.taps == [(5, 5)]


def test_navigator_tap_previous_day_missing_button(timeline_day: date):
    """Return False when the previous-day button is absent."""
    root = ET.fromstring(day_dump_xml(text_xml("Today")))
    nav = Navigator(FakeDriver(), timeline_day)
    assert nav.tap_previous_day(root) is False


def test_navigator_tap_previous_day_missing_bounds(timeline_day: date):
    """Return False when the button has no bounds attribute."""
    xml = (
        '<hierarchy><node class="android.widget.Button" content-desc="Día anterior" '
        'clickable="true"/></hierarchy>'
    )
    nav = Navigator(FakeDriver(), timeline_day)
    assert nav.tap_previous_day(ET.fromstring(xml)) is False
