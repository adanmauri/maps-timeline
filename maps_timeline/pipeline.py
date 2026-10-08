"""Orchestrates the sequential scraping loop (day by day, going backwards)."""

from __future__ import annotations

import json
import traceback
import xml.etree.ElementTree as ET  # nosec B405 — trusted local adb dumps only
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from time import monotonic

from .device import Driver
from .models import DayTimeline
from .navigator import Navigator
from .parser import parse_day, timeline_list_present, timeline_panel_collapsed
from .waits import dump_full_timeline, ensure_timeline_panel_expanded, wait_for_stable_screen

PROGRESS_EVERY = 25  # planned walks: print a progress line every this many days


@dataclass
class ScrapeResult:
    """Outcome of a multi-day scraping run."""

    days_scraped: int
    days_failed: list[str]
    output_path: Path
    days_walked: int = 0  # days visited, captured or only stepped over
    stopped: str | None = None  # why the walk ended early (Ctrl+C, device error), if it did


def _append_jsonl(path: Path, payload: dict) -> None:
    """Append one JSON object as a line to a JSONL file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(payload, ensure_ascii=False, default=str) + "\n")


def _resolve_current_date(
    nav: Navigator, root: ET.Element, today: date, expected: date | None
) -> date:
    """Return the active day, falling back to the arithmetic anchor when needed."""
    current = nav.displayed_date(root)
    if current is not None:
        return current
    return expected if expected is not None else today


def _log_day(timeline: DayTimeline, current: date) -> None:
    """Print a one-line progress message for the parsed day."""
    if not timeline.segments and timeline.summary.visit_count in (None, 0):
        print(f"[·] {current}: empty day.")
        return
    match = timeline.summary_matches()
    flag = "" if match in (True, None) else "  (does not match summary)"
    print(
        f"[✓] {current}: {len(timeline.segments)} segments, "
        f"{timeline.place_visits} visits{flag}"
    )


def _handle_navigation_failure(
    *,
    driver: Driver,
    current: date,
    debug_dir: Path,
    on_error: str,
    failed: list[str],
) -> bool:
    """Record a failed navigation and return True when the loop should stop."""
    debug_dir.mkdir(parents=True, exist_ok=True)
    driver.screenshot(str(debug_dir / f"{current}_no_prev_button.png"))
    print(f"[!] Could not find the 'Previous day' button on {current}.")
    failed.append(str(current))
    return on_error == "abort"


def _save_debug_day(
    debug_dir: Path,
    current: date,
    dump: str,
    driver: Driver,
    *,
    tag: str,
) -> None:
    """Persist XML + screenshot when a day fails to parse as expected."""
    debug_dir.mkdir(parents=True, exist_ok=True)
    stem = debug_dir / f"{current}_{tag}"
    stem.with_suffix(".xml").write_text(dump, encoding="utf-8")
    driver.screenshot(str(stem.with_suffix(".png")))


def _screen_problem(dump: str, *, check_panel: bool) -> tuple[str, str] | None:
    """Return ``(debug tag, message)`` when the dump is not a usable Timeline day view."""
    if not timeline_list_present(dump):
        return "wrong_screen", (
            "The Timeline 'Day' view is not visible. "
            "Open Google Maps → Rutas → Día on the day you want to start from, then retry."
        )
    if check_panel and timeline_panel_collapsed(dump):
        return "collapsed_panel", (
            "The Timeline activity list is collapsed (map-only view). "
            "Swipe the bottom sheet up until the full day list is visible, then retry."
        )
    return None


def _record_day(driver: Driver, dump: str, current: date, debug_dir: Path, out_path: Path) -> None:
    """Parse a captured day, log it, and append it to the JSONL."""
    timeline = parse_day(dump, current)
    if not timeline.segments and (timeline.summary.visit_count or 0) > 0:
        _save_debug_day(debug_dir, current, dump, driver, tag="empty")
        print(
            f"[!] {current}: 0 segments but summary shows "
            f"{timeline.summary.visit_count} visits. Debug saved to {debug_dir}."
        )
    _log_day(timeline, current)
    _append_jsonl(out_path, timeline.model_dump())


def _save_crash(debug_dir: Path, day: date | None, exc: Exception) -> str:
    """Save the traceback of an unexpected error to the debug folder; return a short reason."""
    debug_dir.mkdir(parents=True, exist_ok=True)
    path = debug_dir / f"{day or 'start'}_error.txt"
    path.write_text("".join(traceback.format_exception(exc)), encoding="utf-8")
    return f"{type(exc).__name__}; traceback saved to {path}"


@dataclass(frozen=True)
class _Walk:
    """Fixed inputs of one walk back through the Timeline."""

    driver: Driver
    nav: Navigator
    today: date
    out_path: Path
    debug_dir: Path
    on_error: str
    only_days: frozenset[date] | None  # planned walk: capture only these days


@dataclass
class _WalkState:
    """Progress of one walk, kept current so a walk that stops early still reports it."""

    failed: list[str] = field(default_factory=list)
    scraped: int = 0
    walked: int = 0
    expected: date | None = None  # day the screen should show next
    stable_dump: str | None = None  # screen after the last day change, reused when skipping
    started: float = 0.0  # monotonic() when the walk began
    span: int = 0  # planned walk: days from the first one back to the oldest planned one


def _begin_planned_walk(only_days: frozenset[date], state: _WalkState, first: date) -> None:
    """Size a planned walk from its first day and warn about planned days it cannot reach."""
    state.span = max((first - min(only_days)).days + 1, 1)
    newer = [day for day in only_days if day > first]
    if newer:
        print(
            f"[!] {len(newer)} planned days are newer than {first} and will not be captured. "
            f"Open the Timeline on {max(newer)} to include them."
        )


def _report_progress(state: _WalkState, planned: int, current: date) -> None:
    """Print a progress line every `PROGRESS_EVERY` days of a planned walk."""
    if state.walked % PROGRESS_EVERY:
        return
    per_day = (monotonic() - state.started) / state.walked
    minutes_left = round(per_day * max(state.span - state.walked, 0) / 60)
    print(
        f"[·] {current}: walked {state.walked}/{state.span} days, "
        f"captured {state.scraped}/{planned}, about {minutes_left} min left."
    )


def _step(walk: _Walk, state: _WalkState) -> bool:
    """Visit the displayed day (capture it or step over it), then go back one day.

    Returns False when the walk has to stop.
    """
    only_days = walk.only_days
    if only_days and state.expected is not None and state.expected < min(only_days):
        return False
    capture = only_days is None or state.expected is None or state.expected in only_days
    if capture:
        dump = dump_full_timeline(walk.driver, reset_scroll=state.walked > 0)
    else:
        dump = state.stable_dump if state.stable_dump is not None else walk.driver.dump()
    root = ET.fromstring(dump)  # nosec B314

    current = _resolve_current_date(walk.nav, root, walk.today, state.expected)
    if state.expected is None:
        state.expected = current
        if only_days:
            _begin_planned_walk(only_days, state, current)

    if current != state.expected:
        print(f"[!] Expected date {state.expected} but the app shows {current}. Aborting.")
        state.failed.append(str(state.expected))
        return False

    wanted = only_days is None or current in only_days
    problem = _screen_problem(dump, check_panel=wanted)
    if problem is not None:
        tag, message = problem
        _save_debug_day(walk.debug_dir, current, dump, walk.driver, tag=tag)
        print(f"[!] {message}")
        print(f"    Debug saved to {walk.debug_dir}.")
        state.failed.append(str(current))
        return False

    state.walked += 1
    if wanted:
        _record_day(walk.driver, dump, current, walk.debug_dir, walk.out_path)
        state.scraped += 1
    if only_days:
        _report_progress(state, len(only_days), current)

    state.stable_dump = None
    if not walk.nav.tap_previous_day(root):
        if _handle_navigation_failure(
            driver=walk.driver,
            current=current,
            debug_dir=walk.debug_dir,
            on_error=walk.on_error,
            failed=state.failed,
        ):
            return False
    else:
        state.stable_dump = wait_for_stable_screen(walk.driver.dump, settle=0.8, timeout=15.0)
    state.expected = current - timedelta(days=1)
    return True


def scrape(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    driver: Driver,
    today: date,
    n_days: int,
    out_dir: Path,
    debug_dir: Path | None = None,
    on_error: str = "skip",
    only_days: frozenset[date] | None = None,
) -> ScrapeResult:
    """Walk `n_days` backwards from the displayed day, parsing each one.

    With `only_days` (an export-driven plan), other days are only stepped over: header
    check and "Previous day" tap, no capture. The walk stops after the oldest planned day.
    Ctrl+C or a device error ends the walk early; the days captured so far are kept.
    """
    out_path = out_dir / "timeline.jsonl"
    debug_dir = debug_dir or (out_dir / "debug")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("", encoding="utf-8")
    if only_days is not None and not only_days:
        return ScrapeResult(days_scraped=0, days_failed=[], output_path=out_path)

    walk = _Walk(driver, Navigator(driver, today), today, out_path, debug_dir, on_error, only_days)
    state = _WalkState(started=monotonic())
    stopped: str | None = None
    ensure_timeline_panel_expanded(driver)
    try:
        for _ in range(n_days):
            if not _step(walk, state):
                break
    except KeyboardInterrupt:
        stopped = "interrupted"
    # Lost connection, adb or app errors mid-walk: keep the days already captured.
    except Exception as exc:  # pylint: disable=broad-exception-caught
        stopped = _save_crash(debug_dir, state.expected, exc)
    if stopped is not None:
        print(
            f"[!] Walk stopped early ({stopped}). "
            f"Keeping the {state.scraped} days captured so far."
        )
    return ScrapeResult(
        days_scraped=state.scraped,
        days_failed=state.failed,
        output_path=out_path,
        days_walked=state.walked,
        stopped=stopped,
    )
