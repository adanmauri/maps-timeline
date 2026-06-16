"""Timeline list scroll gestures derived from the current UI dump."""

from __future__ import annotations

import xml.etree.ElementTree as ET  # nosec B405 — trusted local adb dumps only

from .device import Driver
from .parser import (
    DEFAULT_SCREEN_HEIGHT,
    _parse_bounds,
    date_header_top_y,
    parse_segment,
    screen_size_from_dump,
)

# Lane fractions calibrated on 1440x3120; scaled per dump via ``screen_size_from_dump``.
_LANE_Y_MIN_FRAC = 1900 / DEFAULT_SCREEN_HEIGHT
_LANE_Y_MAX_FRAC = 3000 / DEFAULT_SCREEN_HEIGHT
_DEFAULT_LANE_Y_MID_FRAC = 2450 / DEFAULT_SCREEN_HEIGHT
_DEFAULT_LANE_HALF_SPAN_FRAC = 250 / DEFAULT_SCREEN_HEIGHT
_SWIPE_DURATION_MS = 450
_EXPAND_SWIPE_DURATION_MS = 550


def _lane_y_limits(screen_h: int) -> tuple[int, int]:
    """Return vertical bounds for list swipes, below the day-navigation chrome."""
    return int(screen_h * _LANE_Y_MIN_FRAC), int(screen_h * _LANE_Y_MAX_FRAC)


def _segment_lane_coordinates(  # pylint: disable=duplicate-code
    dump_xml: str,
) -> tuple[list[int], list[int]]:
    """Collect button bounds for parseable Timeline segments."""
    xs: list[int] = []
    ys: list[int] = []
    root = ET.fromstring(dump_xml)  # nosec B314
    for node in root.iter("node"):
        if node.get("class") != "android.widget.Button":
            continue
        desc = node.get("content-desc", "")
        bounds = node.get("bounds")
        if not desc or bounds is None or parse_segment(desc) is None:
            continue
        box = _parse_bounds(bounds)
        if box is None:
            continue
        x1, y1, x2, y2 = box
        xs.extend((x1, x2))
        ys.extend((y1, y2))
    return xs, ys


def timeline_scroll_lane(dump_xml: str) -> tuple[int, int, int]:
    """Return ``(center_x, y_start, y_end)`` for a short vertical swipe in the list lane."""
    screen_w, screen_h = screen_size_from_dump(dump_xml)
    min_lane_y, max_lane_y = _lane_y_limits(screen_h)
    xs, ys = _segment_lane_coordinates(dump_xml)
    if xs and ys:
        center_x = (min(xs) + max(xs)) // 2
        y_min = max(min(ys), min_lane_y)
        y_max = min(max(ys), max_lane_y)
    else:
        center_x = screen_w // 2
        half_span = int(screen_h * _DEFAULT_LANE_HALF_SPAN_FRAC)
        mid = int(screen_h * _DEFAULT_LANE_Y_MID_FRAC)
        y_min = mid - half_span
        y_max = mid + half_span

    mid = (y_min + y_max) // 2
    half_span = min(180, max(120, (y_max - y_min) // 4))
    y_start = max(min_lane_y, mid - half_span)
    y_end = min(max_lane_y, mid + half_span)
    if y_end <= y_start:
        y_end = min(max_lane_y, y_start + int(screen_h * _DEFAULT_LANE_HALF_SPAN_FRAC))
    return center_x, y_start, y_end


def swipe_timeline_content_up(driver: Driver, dump_xml: str) -> None:
    """Scroll the Timeline list up (toward the first segment) with a short in-lane swipe."""
    x, y_start, y_end = timeline_scroll_lane(dump_xml)
    driver.swipe(x, y_start, x, y_end, duration_ms=_SWIPE_DURATION_MS)


def swipe_timeline_content_down(driver: Driver, dump_xml: str) -> None:
    """Scroll the Timeline list down (toward the last segment) with a short in-lane swipe."""
    x, y_start, y_end = timeline_scroll_lane(dump_xml)
    driver.swipe(x, y_end, x, y_start, duration_ms=_SWIPE_DURATION_MS)


def expand_timeline_panel(driver: Driver, dump_xml: str) -> None:
    """Swipe up on the Maps bottom sheet to expand the Timeline activity list."""
    screen_w, screen_h = screen_size_from_dump(dump_xml)
    x = screen_w // 2
    header_y = date_header_top_y(dump_xml)
    if header_y is not None:
        y_start = min(screen_h - 80, header_y + max(250, int(screen_h * 0.18)))
        y_end = max(120, int(screen_h * 0.12))
    else:
        y_start = int(screen_h * 0.92)
        y_end = int(screen_h * 0.25)
    driver.swipe(x, y_start, x, y_end, duration_ms=_EXPAND_SWIPE_DURATION_MS)
