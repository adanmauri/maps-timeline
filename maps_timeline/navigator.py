"""Navigation within the Timeline: read the date and step back one day.

The source of truth for which day is being scraped is date arithmetic; the
on-screen header is only used to *verify* that the navigation worked.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET  # nosec B405 — trusted local adb dumps only
from datetime import date, timedelta

from .device import Driver

_BOUNDS_RE = re.compile(r"\[(\d+),(\d+)]\[(\d+),(\d+)]")
_MONTHS = {
    "Jan": 1,
    "Feb": 2,
    "Mar": 3,
    "Apr": 4,
    "May": 5,
    "Jun": 6,
    "Jul": 7,
    "Aug": 8,
    "Sep": 9,
    "Oct": 10,
    "Nov": 11,
    "Dec": 12,
}
_HEADER_DATE_RE = re.compile(r"^[A-Z][a-z]{2} ([A-Z][a-z]{2}) (\d{1,2}), (\d{4})$")
# "Previous day" button accessibility label (Spanish UI string).
_PREV_DAY_DESC = "Día anterior"


def center_of(bounds: str) -> tuple[int, int]:
    """'[x1,y1][x2,y2]' -> (cx, cy)."""
    m = _BOUNDS_RE.match(bounds)
    if m is None:
        raise ValueError(f"Unexpected bounds format: {bounds!r}")
    x1, y1, x2, y2 = map(int, m.groups())
    return (x1 + x2) // 2, (y1 + y2) // 2


def resolve_header_date(text: str, today: date) -> date | None:
    """Convert the (English) header text into a date. None if it cannot be parsed."""
    text = text.strip()
    if text == "Today":
        return today
    if text == "Yesterday":
        return today - timedelta(days=1)
    if m := _HEADER_DATE_RE.match(text):
        month = _MONTHS.get(m.group(1))
        if month:
            return date(int(m.group(3)), month, int(m.group(2)))
    return None


def _find_node(root: ET.Element, predicate) -> ET.Element | None:
    """Return the first node in `root` that satisfies `predicate`."""
    for node in root.iter("node"):
        if predicate(node):
            return node
    return None


class Navigator:
    """Read the displayed date and tap the 'Previous day' control."""

    def __init__(self, driver: Driver, today: date):
        """Bind a driver and the reference date for relative headers."""
        self.driver = driver
        self.today = today

    def header_text(self, root: ET.Element) -> str | None:
        """Return the raw header date string from a UI dump root."""
        from .parser import read_header_text  # pylint: disable=import-outside-toplevel

        return read_header_text(root)

    def displayed_date(self, root: ET.Element) -> date | None:
        """Return the date shown in the header, or None if it cannot be parsed."""
        text = self.header_text(root)
        return resolve_header_date(text, self.today) if text else None

    def tap_previous_day(self, root: ET.Element) -> bool:
        """Tap the previous-day button. Return False when it is not on screen."""
        node = _find_node(
            root,
            lambda n: n.get("content-desc") == _PREV_DAY_DESC and n.get("clickable") == "true",
        )
        if node is None:
            return False
        bounds = node.get("bounds")
        if bounds is None:
            return False
        x, y = center_of(bounds)
        self.driver.tap_xy(x, y)
        return True
