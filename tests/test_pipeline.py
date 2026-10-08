"""Tests for the scraping pipeline."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from maps_timeline.pipeline import scrape
from tests.conftest import (
    FakeDriver,
    MinimalDriver,
    button_xml,
    day_dump_xml,
    patch_instant_waits,
    text_xml,
)


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


class SteppingDriver(MinimalDriver):
    """Driver whose screen moves one day back on every tap."""

    def __init__(self, dumps: list[str]) -> None:
        """Start on the first dump of the list."""
        self.dumps = dumps
        self.index = 0

    def dump(self) -> str:
        """Return the screen for the current day (the last one repeats)."""
        return self.dumps[min(self.index, len(self.dumps) - 1)]

    def tap_xy(self, x: int, y: int) -> None:
        """Treat any tap as 'Previous day'."""
        del x, y
        self.index += 1


def _patch_planned_walk(monkeypatch) -> list[bool]:
    """Stub waits and record each full capture's reset_scroll flag."""
    captures: list[bool] = []

    def fake_full_dump(driver, *, reset_scroll=False):
        """Record the capture and return the current screen."""
        captures.append(reset_scroll)
        return driver.dump()

    monkeypatch.setattr("maps_timeline.pipeline.dump_full_timeline", fake_full_dump)
    monkeypatch.setattr(
        "maps_timeline.pipeline.wait_for_stable_screen", lambda get_dump, **_kwargs: get_dump()
    )
    monkeypatch.setattr("maps_timeline.pipeline.ensure_timeline_panel_expanded", lambda _d: "")
    return captures


def test_scrape_only_days_steps_over_other_days(tmp_path: Path, monkeypatch):
    """Capture only planned days and stop after the oldest one."""
    captures = _patch_planned_walk(monkeypatch)
    driver = SteppingDriver(
        [
            _day_xml("Today"),
            _day_xml("Yesterday"),
            _day_xml("Mon Jun 8, 2026"),
            _day_xml("Sun Jun 7, 2026"),
        ]
    )
    result = scrape(
        driver,
        today=date(2026, 6, 10),
        n_days=10,
        out_dir=tmp_path,
        only_days=frozenset({date(2026, 6, 8)}),
    )
    assert (result.days_scraped, result.days_walked) == (1, 3)
    assert not result.days_failed
    assert captures == [False, True]  # start day is read in full once, then only Jun 8
    lines = (tmp_path / "timeline.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert [json.loads(line)["day"] for line in lines] == ["2026-06-08"]


def test_scrape_only_days_empty_plan(tmp_path: Path, monkeypatch):
    """Do nothing when the plan has no days."""
    _patch_planned_walk(monkeypatch)
    driver = SteppingDriver([_day_xml("Today")])
    result = scrape(
        driver, today=date(2026, 6, 10), n_days=5, out_dir=tmp_path, only_days=frozenset()
    )
    assert (result.days_scraped, result.days_walked) == (0, 0)
    assert driver.index == 0
    assert (tmp_path / "timeline.jsonl").read_text(encoding="utf-8") == ""


def test_scrape_only_days_rereads_screen_after_failed_tap(tmp_path: Path, monkeypatch):
    """After a failed 'Previous day' tap, re-read the screen and catch the date drift."""
    _patch_planned_walk(monkeypatch)
    driver = SteppingDriver([_day_xml("Today"), _day_xml("Yesterday", with_prev=False)])
    result = scrape(
        driver,
        today=date(2026, 6, 10),
        n_days=10,
        out_dir=tmp_path,
        on_error="skip",
        only_days=frozenset({date(2026, 6, 7)}),
    )
    assert result.days_scraped == 0
    assert result.days_failed == ["2026-06-09", "2026-06-08"]


def test_scrape_only_days_stops_on_wrong_screen(tmp_path: Path, monkeypatch, capsys):
    """A skipped day that is not the Timeline view still stops the walk."""
    _patch_planned_walk(monkeypatch)
    driver = SteppingDriver([_day_xml("Today"), "<hierarchy/>"])
    result = scrape(
        driver,
        today=date(2026, 6, 10),
        n_days=10,
        out_dir=tmp_path,
        only_days=frozenset({date(2026, 6, 7)}),
    )
    assert result.days_failed == ["2026-06-09"]
    assert (tmp_path / "debug" / "2026-06-09_wrong_screen.xml").exists()
    assert "Timeline 'Day' view is not visible" in capsys.readouterr().out


class FailingDriver(SteppingDriver):
    """Stepping driver whose screen read fails once the walk reaches a given day index."""

    def __init__(self, dumps: list[str], fail_at: int, error: BaseException) -> None:
        """Fail with `error` when reading the screen at day index `fail_at`."""
        super().__init__(dumps)
        self.fail_at = fail_at
        self.error = error

    def dump(self) -> str:
        """Return the current screen, or raise once the failing day is reached."""
        if self.index >= self.fail_at:
            raise self.error
        return super().dump()


def _three_days() -> list[str]:
    """Screens for 2026-06-10, 2026-06-09 and 2026-06-08."""
    return [_day_xml("Today"), _day_xml("Yesterday"), _day_xml("Mon Jun 8, 2026")]


def test_scrape_keeps_captured_days_on_ctrl_c(tmp_path: Path, monkeypatch, capsys):
    """Ctrl+C ends the walk but keeps the days already written."""
    _patch_planned_walk(monkeypatch)
    driver = FailingDriver(_three_days(), fail_at=2, error=KeyboardInterrupt())
    result = scrape(driver, today=date(2026, 6, 10), n_days=5, out_dir=tmp_path)
    assert (result.days_scraped, result.stopped) == (2, "interrupted")
    assert len((tmp_path / "timeline.jsonl").read_text(encoding="utf-8").splitlines()) == 2
    assert "Walk stopped early (interrupted). Keeping the 2 days" in capsys.readouterr().out


def test_scrape_keeps_captured_days_on_device_error(tmp_path: Path, monkeypatch):
    """A device error ends the walk, keeps the captured days and saves the traceback."""
    _patch_planned_walk(monkeypatch)
    driver = FailingDriver(_three_days(), fail_at=1, error=RuntimeError("device offline"))
    result = scrape(driver, today=date(2026, 6, 10), n_days=5, out_dir=tmp_path)
    assert result.days_scraped == 1
    assert result.stopped is not None and result.stopped.startswith("RuntimeError;")
    # The screen read that failed was the wait after leaving 2026-06-10.
    trace = (tmp_path / "debug" / "2026-06-10_error.txt").read_text(encoding="utf-8")
    assert "device offline" in trace


def test_scrape_planned_walk_reports_progress(tmp_path: Path, monkeypatch, capsys):
    """Print walked/captured counts and a time estimate every few days of a planned walk."""
    _patch_planned_walk(monkeypatch)
    monkeypatch.setattr("maps_timeline.pipeline.PROGRESS_EVERY", 2)
    clock = iter([0.0, 120.0])
    monkeypatch.setattr("maps_timeline.pipeline.monotonic", lambda: next(clock))
    driver = SteppingDriver(_three_days() + [_day_xml("Sun Jun 7, 2026")])
    scrape(
        driver,
        today=date(2026, 6, 10),
        n_days=10,
        out_dir=tmp_path,
        only_days=frozenset({date(2026, 6, 7)}),
    )
    assert "[·] 2026-06-09: walked 2/4 days, captured 0/1, about 2 min left." in (
        capsys.readouterr().out
    )


def test_scrape_planned_walk_warns_about_newer_planned_days(tmp_path: Path, monkeypatch, capsys):
    """Planned days newer than the starting screen cannot be reached walking back."""
    _patch_planned_walk(monkeypatch)
    driver = SteppingDriver([_day_xml("Yesterday"), _day_xml("Mon Jun 8, 2026")])
    result = scrape(
        driver,
        today=date(2026, 6, 10),
        n_days=10,
        out_dir=tmp_path,
        only_days=frozenset({date(2026, 6, 10), date(2026, 6, 8)}),
    )
    assert result.days_scraped == 1
    assert (
        "1 planned days are newer than 2026-06-09 and will not be captured. "
        "Open the Timeline on 2026-06-10 to include them."
    ) in capsys.readouterr().out
