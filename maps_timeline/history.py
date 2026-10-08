"""Scrape history: the latest capture of each day across every run.

Each run writes its own raw JSONL under data/runs/<stamp>/raw/. When the official export
is in play, both the merged dataset and the planner look at all of them together, so a
day captured once (in any run, even one that was interrupted before the merge) is reused
instead of walked to again.

A capture is **complete** when the run started after the day ended. A day captured on
its own date (the run's stamp date) may still be missing its last hours, so the planner
captures it again while the official export does not cover it.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from .normalize import read_days
from .paths import run_date


@dataclass(frozen=True)
class ScrapeHistory:
    """Latest capture of each scraped day, and which of those captures are complete."""

    days: list[dict[str, Any]]  # raw JSONL day objects, one per day, sorted by day
    complete: frozenset[date]  # days captured after they ended: never worth revisiting


def load_history(sources: Iterable[Path]) -> ScrapeHistory:
    """Read raw JSONL files in order; a later capture of a day replaces an earlier one.

    Missing files are skipped. Files outside a versioned run count as complete captures.
    """
    latest: dict[date, dict[str, Any]] = {}
    complete: set[date] = set()
    for path in sources:
        if not path.is_file():
            continue
        captured_on = run_date(path.parent.parent)
        for day_obj in read_days(path):
            day = date.fromisoformat(str(day_obj["day"]))
            latest[day] = day_obj
            if captured_on is None or day < captured_on:
                complete.add(day)
    return ScrapeHistory([latest[day] for day in sorted(latest)], frozenset(complete))
