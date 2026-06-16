"""Orchestrates the sequential scraping loop (day by day, going backwards)."""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET  # nosec B405 — trusted local adb dumps only
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

from .device import Driver
from .models import DayTimeline
from .navigator import Navigator
from .parser import parse_day, timeline_list_present, timeline_panel_collapsed
from .waits import dump_full_timeline, ensure_timeline_panel_expanded, wait_for_stable_screen


@dataclass
class ScrapeResult:
    """Outcome of a multi-day scraping run."""

    days_scraped: int
    days_failed: list[str]
    output_path: Path


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


def scrape(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    driver: Driver,
    today: date,
    n_days: int,
    out_dir: Path,
    debug_dir: Path | None = None,
    on_error: str = "skip",
) -> ScrapeResult:
    """Walk `n_days` backwards from the displayed day, parsing each one."""
    nav = Navigator(driver, today)
    out_path = out_dir / "timeline.jsonl"
    debug_dir = debug_dir or (out_dir / "debug")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("", encoding="utf-8")

    failed: list[str] = []
    scraped = 0
    expected: date | None = None

    ensure_timeline_panel_expanded(driver)

    for _ in range(n_days):
        dump = dump_full_timeline(driver, reset_scroll=scraped > 0)
        root = ET.fromstring(dump)  # nosec B314

        current = _resolve_current_date(nav, root, today, expected)
        if expected is None:
            expected = current

        if current != expected:
            print(f"[!] Expected date {expected} but the app shows {current}. Aborting.")
            failed.append(str(expected))
            break

        if not timeline_list_present(dump):
            _save_debug_day(debug_dir, current, dump, driver, tag="wrong_screen")
            print(
                "[!] The Timeline 'Day' view is not visible. "
                "Open Google Maps → Rutas → Día on the day you want to start from, then retry."
            )
            print(f"    Debug saved to {debug_dir}.")
            failed.append(str(current))
            break

        if timeline_panel_collapsed(dump):
            _save_debug_day(debug_dir, current, dump, driver, tag="collapsed_panel")
            print(
                "[!] The Timeline activity list is collapsed (map-only view). "
                "Swipe the bottom sheet up until the full day list is visible, then retry."
            )
            print(f"    Debug saved to {debug_dir}.")
            failed.append(str(current))
            break

        timeline = parse_day(dump, current)
        if not timeline.segments and (timeline.summary.visit_count or 0) > 0:
            _save_debug_day(debug_dir, current, dump, driver, tag="empty")
            print(
                f"[!] {current}: 0 segments but summary shows "
                f"{timeline.summary.visit_count} visits. Debug saved to {debug_dir}."
            )
        _log_day(timeline, current)
        _append_jsonl(out_path, timeline.model_dump())
        scraped += 1

        if not nav.tap_previous_day(root):
            if _handle_navigation_failure(
                driver=driver,
                current=current,
                debug_dir=debug_dir,
                on_error=on_error,
                failed=failed,
            ):
                break
        else:
            wait_for_stable_screen(driver.dump, settle=0.8, timeout=15.0)
        expected = current - timedelta(days=1)

    return ScrapeResult(days_scraped=scraped, days_failed=failed, output_path=out_path)
