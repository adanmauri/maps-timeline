"""Explicit waits: no magic `sleep`s.

The core idea is to wait until the screen is "stable" (two consecutive identical
dumps), which signals that the transition animation has finished.
"""

from __future__ import annotations

import hashlib
import time
import xml.etree.ElementTree as ET  # nosec B405 — trusted local adb dumps only
from collections.abc import Callable

from .device import Driver
from .parser import (
    count_timeline_segments,
    is_richer_timeline_dump,
    parse_summary,
    timeline_anchor_flags,
    timeline_list_present,
    timeline_panel_needs_expand,
)
from .scroll import (
    expand_timeline_panel,
    swipe_timeline_content_down,
    swipe_timeline_content_up,
)

_MAX_SCROLL_TO_TOP = 2
_MAX_SCROLL_TO_TOP_WITH_VISITS = 6
_MAX_RESET_SCROLL_AFTER_DAY_CHANGE = 3
_MAX_TIMELINE_SCROLLS = 4
_MAX_PANEL_EXPAND_ATTEMPTS = 3
_SCROLL_PAUSE_S = 0.4


def _scroll_timeline_to_top(
    driver: Driver, dump_xml: str, *, max_swipes: int = _MAX_SCROLL_TO_TOP
) -> None:
    """Nudge the Timeline list upward when a day loaded with no visible segments."""
    for _ in range(max_swipes):
        swipe_timeline_content_up(driver, dump_xml)
        time.sleep(_SCROLL_PAUSE_S)


def _reset_timeline_scroll_after_day_change(driver: Driver, dump_xml: str) -> None:
    """Scroll the inherited list position back toward the top after changing days."""
    _scroll_timeline_to_top(driver, dump_xml, max_swipes=_MAX_RESET_SCROLL_AFTER_DAY_CHANGE)


def _sig(xml: str) -> str:
    """Hash a dump for stable-screen comparison (non-cryptographic)."""
    return hashlib.sha1(xml.encode("utf-8"), usedforsecurity=False).hexdigest()


def wait_for_stable_screen(
    get_dump: Callable[[], str],
    settle: float = 0.6,
    timeout: float = 12.0,
) -> str:
    """Return the dump once two consecutive reads match."""
    deadline = time.monotonic() + timeout
    prev = get_dump()
    while time.monotonic() < deadline:
        time.sleep(settle)
        cur = get_dump()
        if _sig(cur) == _sig(prev):
            return cur
        prev = cur
    return prev  # timeout: return whatever we have


def ensure_timeline_panel_expanded(
    driver: Driver,
    *,
    get_dump: Callable[[], str] | None = None,
) -> str:
    """Swipe the bottom sheet up until the Timeline list is ready to scrape."""
    read = get_dump or driver.dump
    dump = wait_for_stable_screen(read, settle=0.4, timeout=8.0)
    for _ in range(_MAX_PANEL_EXPAND_ATTEMPTS):
        if not timeline_list_present(dump) or not timeline_panel_needs_expand(dump):
            return dump
        expand_timeline_panel(driver, dump)
        time.sleep(_SCROLL_PAUSE_S)
        dump = wait_for_stable_screen(read, settle=0.5, timeout=10.0)
    return dump


def dump_full_timeline(
    driver: Driver,
    *,
    get_dump: Callable[[], str] | None = None,
    reset_scroll: bool = False,
) -> str:
    """Return a dump after scrolling so lazy-loaded bottom segments are included."""
    read = get_dump or driver.dump
    dump = wait_for_stable_screen(read, settle=0.6, timeout=12.0)
    if not timeline_list_present(dump):
        return dump

    if reset_scroll:
        _reset_timeline_scroll_after_day_change(driver, dump)
        dump = wait_for_stable_screen(read, settle=0.3, timeout=6.0)

    best_dump = dump
    best_count = count_timeline_segments(dump)

    if best_count == 0:
        root = ET.fromstring(dump)  # nosec B314
        visit_count = parse_summary(root).visit_count or 0
        top_swipes = _MAX_SCROLL_TO_TOP_WITH_VISITS if visit_count > 0 else _MAX_SCROLL_TO_TOP
        _scroll_timeline_to_top(driver, dump, max_swipes=top_swipes)
        dump = wait_for_stable_screen(read, settle=0.3, timeout=6.0)
        best_dump = dump
        best_count = count_timeline_segments(dump)

    if best_count == 0:
        return best_dump

    for _ in range(_MAX_TIMELINE_SCROLLS):
        swipe_timeline_content_down(driver, best_dump)
        time.sleep(_SCROLL_PAUSE_S)
        dump = wait_for_stable_screen(read, settle=0.3, timeout=6.0)
        if is_richer_timeline_dump(dump, best_dump):
            best_dump = dump
            best_count = count_timeline_segments(dump)
            continue
        has_departure, has_arrival = timeline_anchor_flags(best_dump)
        if has_departure and not has_arrival:
            continue
        break
    return best_dump


def wait_until(predicate: Callable[[], bool], timeout: float = 10.0, poll: float = 0.4) -> bool:
    """Poll `predicate` until it returns True or `timeout` seconds elapse."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(poll)
    return False
