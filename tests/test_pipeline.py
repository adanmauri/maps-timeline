"""Tests for the scraping pipeline."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from maps_timeline.pipeline import scrape
from tests.conftest import FakeDriver, button_xml, day_dump_xml, patch_instant_waits, text_xml


def _day_xml(header: str, *, with_prev: bool = True) -> str:
    parts = [text_xml(header), text_xml("18 km"), text_xml("1 visitas")]
    parts.append(
        button_xml(
            "C. 1, Hora de salida: 4:08 PM, C. 1, City",
            bounds="[0,0][1,1]",
        )
    )
    if with_prev:
        parts.append(button_xml("Día anterior", clickable=True, bounds="[0,0][10,10]"))
    return day_dump_xml(*parts)


def test_scrape_writes_jsonl(tmp_path: Path):
    """Scrape one day and append a JSONL record."""
    xml = _day_xml("Today")
    driver = FakeDriver(dumps=[xml, xml])
    result = scrape(driver, today=date(2026, 6, 10), n_days=1, out_dir=tmp_path)
    assert result.days_scraped == 1
    assert not result.days_failed
    lines = (tmp_path / "timeline.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    payload = json.loads(lines[0])
    assert payload["day"] == "2026-06-10"


def test_scrape_detects_date_drift(tmp_path: Path, capsys):
    """Abort when the header date does not match the expected anchor."""
    xml = _day_xml("Sat Jun 6, 2026")
    driver = FakeDriver(dumps=[xml, xml])
    result = scrape(driver, today=date(2026, 6, 10), n_days=2, out_dir=tmp_path)
    assert result.days_scraped == 1
    assert result.days_failed == ["2026-06-05"]
    assert "Expected date" in capsys.readouterr().out


def test_scrape_navigation_failure_skip(tmp_path: Path, capsys):
    """Continue after a missing previous-day button when on_error=skip."""
    xml = _day_xml("Today", with_prev=False)
    driver = FakeDriver(dumps=[xml, xml])
    result = scrape(
        driver,
        today=date(2026, 6, 10),
        n_days=1,
        out_dir=tmp_path,
        on_error="skip",
    )
    assert result.days_scraped == 1
    assert result.days_failed == ["2026-06-10"]
    assert driver.screenshots
    assert "Previous day" in capsys.readouterr().out


def test_scrape_navigation_failure_abort(tmp_path: Path):
    """Stop immediately when on_error=abort."""
    xml = _day_xml("Today", with_prev=False)
    driver = FakeDriver(dumps=[xml, xml])
    result = scrape(
        driver,
        today=date(2026, 6, 10),
        n_days=3,
        out_dir=tmp_path,
        on_error="abort",
    )
    assert result.days_scraped == 1
    assert result.days_failed == ["2026-06-10"]


def test_scrape_truncates_existing_jsonl(tmp_path: Path):
    """Replace an existing JSONL file instead of appending duplicate days."""
    xml = _day_xml("Today")
    driver = FakeDriver(dumps=[xml, xml, xml, xml])
    scrape(driver, today=date(2026, 6, 10), n_days=1, out_dir=tmp_path)
    scrape(driver, today=date(2026, 6, 10), n_days=1, out_dir=tmp_path)
    lines = (tmp_path / "timeline.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1


def test_scrape_empty_day_and_summary_mismatch(tmp_path: Path, capsys):
    """Log empty days and flag summary mismatches."""
    xml = day_dump_xml(
        text_xml("Today"),
        text_xml("0 visitas"),
        button_xml("Día anterior", clickable=True),
    )
    driver = FakeDriver(dumps=[xml, xml, xml, xml])
    result = scrape(driver, today=date(2026, 6, 10), n_days=1, out_dir=tmp_path)
    assert result.days_scraped == 1
    out = capsys.readouterr().out
    assert "empty day" in out


def test_scrape_uses_fallback_date_when_header_missing(tmp_path: Path):
    """Trust today's date when the header cannot be read."""
    xml = day_dump_xml(
        button_xml("En automóvil, 10 min, 2 km, De 4:49 PM a 4:59 PM"),
        button_xml("Día anterior", clickable=True),
    )
    driver = FakeDriver(dumps=[xml, xml])
    scrape(driver, today=date(2026, 6, 10), n_days=1, out_dir=tmp_path)
    payload = json.loads((tmp_path / "timeline.jsonl").read_text(encoding="utf-8"))
    assert payload["day"] == "2026-06-10"


def test_scrape_aborts_when_timeline_is_not_visible(tmp_path: Path, monkeypatch, capsys):
    """Stop early with a clear message when Maps is not on the Timeline day view."""
    driver = FakeDriver(dumps=["<hierarchy/>"] * 6)
    patch_instant_waits(monkeypatch)
    result = scrape(driver, today=date(2026, 6, 10), n_days=3, out_dir=tmp_path)
    assert result.days_scraped == 0
    assert result.days_failed == ["2026-06-10"]
    assert (tmp_path / "debug" / "2026-06-10_wrong_screen.xml").exists()
    assert "Timeline 'Day' view is not visible" in capsys.readouterr().out


def test_scrape_aborts_when_activity_panel_is_collapsed(tmp_path: Path, monkeypatch, capsys):
    """Stop early when only the map is visible and the activity list is collapsed."""
    xml = day_dump_xml(text_xml("Today"), button_xml("Día anterior", clickable=True))
    driver = FakeDriver(dumps=[xml] * 6)
    patch_instant_waits(monkeypatch, reset_after_day_change=True)
    result = scrape(driver, today=date(2026, 6, 10), n_days=3, out_dir=tmp_path)
    assert result.days_scraped == 0
    assert result.days_failed == ["2026-06-10"]
    assert (tmp_path / "debug" / "2026-06-10_collapsed_panel.xml").exists()
    assert "activity list is collapsed" in capsys.readouterr().out


def test_scrape_saves_debug_when_summary_has_visits_but_no_segments(
    tmp_path: Path, monkeypatch, capsys
):
    """Persist XML and a screenshot when the summary and timeline disagree."""
    xml = day_dump_xml(
        text_xml("Wed Jun 3, 2026"),
        text_xml("1 visitas"),
        button_xml("Día anterior", clickable=True),
    )
    driver = FakeDriver(dumps=[xml] * 12)
    patch_instant_waits(monkeypatch)
    scrape(driver, today=date(2026, 6, 10), n_days=1, out_dir=tmp_path)
    debug_xml = tmp_path / "debug" / "2026-06-03_empty.xml"
    assert debug_xml.exists()
    assert driver.screenshots == [str(tmp_path / "debug" / "2026-06-03_empty.png")]
    assert "Debug saved" in capsys.readouterr().out


def test_scrape_waits_after_successful_previous_day_tap(tmp_path: Path, monkeypatch):
    """Wait for the next day to settle after tapping 'Previous day'."""
    xml_today = _day_xml("Today")
    xml_yesterday = _day_xml("Yesterday")
    driver = FakeDriver(dumps=[xml_today, xml_today, xml_yesterday, xml_yesterday, xml_yesterday])
    waits_after_tap: list[bool] = []

    def track_wait(get_dump, settle=0.6, timeout=12.0):
        """Record that wait_for_stable_screen was invoked."""
        del settle, timeout
        waits_after_tap.append(True)
        return get_dump()

    patch_instant_waits(monkeypatch, stable_screen_fn=track_wait)
    monkeypatch.setattr("maps_timeline.pipeline.wait_for_stable_screen", track_wait)
    scrape(driver, today=date(2026, 6, 10), n_days=2, out_dir=tmp_path)
    assert waits_after_tap
