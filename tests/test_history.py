"""Tests for the cumulative scrape history across runs."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from maps_timeline.history import load_history
from tests.conftest import scraped_visit_day, write_run_scrape


def test_load_history_latest_capture_wins_and_tracks_complete_days(tmp_path: Path):
    """A later run replaces a day; a day captured on the run's own date is partial."""
    first = write_run_scrape(
        tmp_path,
        "2026-06-08_100000",
        scraped_visit_day("2026-06-07"),
        scraped_visit_day("2026-06-08", "8:00 AM", "9:00 AM"),
    )
    second = write_run_scrape(
        tmp_path,
        "2026-06-10_090000",
        scraped_visit_day("2026-06-10"),
        scraped_visit_day("2026-06-08", "1:00 PM", "2:00 PM"),
    )
    history = load_history([first, second])
    assert [day["day"] for day in history.days] == ["2026-06-07", "2026-06-08", "2026-06-10"]
    assert history.days[1]["segments"][0]["start_time"] == "1:00 PM"
    assert history.complete == frozenset({date(2026, 6, 7), date(2026, 6, 8)})


def test_load_history_outside_runs_and_missing_files(tmp_path: Path):
    """Files outside a versioned run count as complete; missing files are skipped."""
    flat = tmp_path / "timeline.jsonl"
    flat.write_text(scraped_visit_day("2026-06-10") + "\n", encoding="utf-8")
    history = load_history([tmp_path / "missing.jsonl", flat])
    assert [day["day"] for day in history.days] == ["2026-06-10"]
    assert history.complete == frozenset({date(2026, 6, 10)})
