"""Tests for the Typer CLI."""

from __future__ import annotations

import importlib
import sys
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock

import pandas as pd
import pytest
from typer.testing import CliRunner

from maps_timeline import paths
from maps_timeline.cli import app, main, read_header_text_safe
from maps_timeline.pipeline import ScrapeResult
from tests.conftest import (
    button_xml,
    day_dump_xml,
    scraped_visit_day,
    text_xml,
    write_run_scrape,
)

runner = CliRunner()
TODAY = date(2026, 6, 10)
RECENT_DAYS = frozenset({date(2026, 6, 7), date(2026, 6, 8), date(2026, 6, 9), TODAY})


class FixedDate(date):
    """`date` whose today() is pinned, so export-driven plans are deterministic."""

    @classmethod
    def today(cls) -> FixedDate:
        """Return the pinned day the tests plan from."""
        return cls(TODAY.year, TODAY.month, TODAY.day)


@pytest.fixture
def fixed_today(monkeypatch) -> date:
    """Pin the CLI's notion of today to 2026-06-10."""
    monkeypatch.setattr("maps_timeline.cli.date", FixedDate)
    return TODAY


@pytest.fixture(name="geocoder_kwargs")
def fixture_geocoder_kwargs(monkeypatch) -> list[dict[str, object]]:
    """Replace the Nominatim geocoder with a fake; return the arguments each one was built with."""
    created: list[dict[str, object]] = []

    class FakeGeocoder:
        """Record constructor kwargs for the CLI geocode path."""

        def __init__(self, **kwargs):
            """Store initialization kwargs for assertions."""
            created.append(kwargs)

        def geocode(self, _address: str | None) -> tuple[float | None, float | None]:
            """Return a fixed coordinate pair."""
            return (1.0, 2.0)

        def close(self) -> None:
            """No-op close hook for pylint public-method parity."""

    monkeypatch.setattr("maps_timeline.geocode.NominatimGeocoder", FakeGeocoder)
    return created


def _fake_device(monkeypatch) -> None:
    """Replace the driver factory with a healthy fake device."""
    monkeypatch.setattr(
        "maps_timeline.device.make_driver",
        lambda **kwargs: MagicMock(dump=lambda: "<hierarchy/>", is_healthy=lambda: True),
    )


def _fake_scrape(
    monkeypatch,
    output_path: Path | None = None,
    days_scraped: int = 1,
    days_failed: list[str] | None = None,
) -> None:
    """Fake the device and a scrape that wrote `output_path` (default: in the run's raw folder)."""
    _fake_device(monkeypatch)
    monkeypatch.setattr(
        "maps_timeline.pipeline.scrape",
        lambda *args, **kwargs: ScrapeResult(
            days_scraped=days_scraped,
            days_failed=days_failed or [],
            output_path=output_path or kwargs["out_dir"] / "timeline.jsonl",
        ),
    )


def test_cli_help():
    """Expose all commands in --help output."""
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "scrape" in result.stdout
    assert "normalize" in result.stdout
    assert "run" in result.stdout


def test_parse_file_command(tmp_path: Path):
    """Parse a saved dump via the CLI."""
    xml = day_dump_xml(
        text_xml("Sat Jun 6, 2026"),
        button_xml("Cafe, De 4:59 PM a 5:59 PM, Main 1"),
    )
    dump = tmp_path / "dump.xml"
    dump.write_text(xml, encoding="utf-8")
    result = runner.invoke(app, ["parse-file", str(dump), "--day", "2026-06-06"])
    assert result.exit_code == 0
    assert "segments" in result.stdout


def test_parse_file_uses_header_when_day_omitted(tmp_path: Path):
    """Infer the day from the dump header when --day is not passed."""
    xml = day_dump_xml(
        text_xml("Today"),
        button_xml("Cafe, De 4:59 PM a 5:59 PM, Main 1"),
    )
    dump = tmp_path / "dump.xml"
    dump.write_text(xml, encoding="utf-8")
    result = runner.invoke(app, ["parse-file", str(dump)])
    assert result.exit_code == 0
    assert str(date.today()) in result.stdout


def test_read_header_text_safe_without_header():
    """Return None when the dump has no recognizable header."""
    assert read_header_text_safe("<hierarchy/>") is None


def test_stats_missing_dataset(tmp_path: Path):
    """Exit with code 1 when the dataset file is missing."""
    missing = tmp_path / "missing.parquet"
    result = runner.invoke(app, ["stats", "--source", str(missing)])
    assert result.exit_code == 1
    assert "No dataset found" in result.stdout


@pytest.mark.usefixtures("isolated_paths")
def test_stats_without_latest_run():
    """Exit with code 1 when no versioned export runs exist yet."""
    result = runner.invoke(app, ["stats"])
    assert result.exit_code == 1
    assert "No export runs found" in result.stdout


@pytest.mark.usefixtures("isolated_paths")
def test_normalize_without_latest_run():
    """Exit with code 1 when normalize defaults are used before any scrape."""
    result = runner.invoke(app, ["normalize"])
    assert result.exit_code == 1
    assert "No export runs found" in result.stdout


def test_stats_falls_back_to_csv(tmp_path: Path):
    """Load CSV when the parquet path does not exist."""
    csv_path = tmp_path / "timeline.csv"
    pd.DataFrame(
        [{"day": "2026-06-06", "type": "activity", "title": "Walk", "duration_min": 5.0}]
    ).to_csv(csv_path, index=False)
    parquet_path = tmp_path / "timeline.parquet"
    result = runner.invoke(app, ["stats", "--source", str(parquet_path)])
    assert result.exit_code == 0
    assert "Google Maps Timeline - summary" in result.stdout


def test_normalize_command(sample_jsonl, tmp_path: Path):
    """Run the normalize command against a sample JSONL file."""
    out = tmp_path / "clean"
    result = runner.invoke(
        app,
        ["normalize", "--jsonl", str(sample_jsonl), "--out", str(out)],
    )
    assert result.exit_code == 0
    assert (out / "timeline.csv").exists()


def test_normalize_with_geocode_flag(sample_jsonl, tmp_path: Path, geocoder_kwargs):
    """Initialize a geocoder when --geocode is passed."""

    out = tmp_path / "clean"
    result = runner.invoke(
        app,
        [
            "normalize",
            "--jsonl",
            str(sample_jsonl),
            "--out",
            str(out),
            "--geocode",
            "--nominatim-email",
            "me@example.com",
        ],
    )
    assert result.exit_code == 0
    assert geocoder_kwargs[0]["user_agent"] == "maps-timeline/0.1 (me@example.com)"


def test_run_command(monkeypatch, tmp_path: Path, sample_jsonl: Path):
    """Run scrape, normalize, and stats in one invocation."""
    raw = tmp_path / "raw"
    clean = tmp_path / "clean"
    _fake_scrape(monkeypatch, sample_jsonl)
    result = runner.invoke(
        app,
        ["run", "--days", "1", "--raw-out", str(raw), "--clean-out", str(clean)],
    )
    assert result.exit_code == 0
    assert "[1/3] Scraping Timeline..." in result.stdout
    assert "[2/3] Normalizing dataset..." in result.stdout
    assert "[3/3] Summary:" in result.stdout
    assert "Google Maps Timeline - summary" in result.stdout
    assert (clean / "timeline.csv").exists()


@pytest.mark.usefixtures("isolated_paths")
def test_run_command_versioned_run(monkeypatch, sample_jsonl: Path):
    """Create one versioned export run when run output flags are omitted."""
    _fake_device(monkeypatch)

    def fake_scrape(_driver, today, n_days, out_dir, **kwargs):
        """Write through to the requested raw folder and return its JSONL path."""
        del today, n_days, kwargs
        out_dir.mkdir(parents=True, exist_ok=True)
        output_path = out_dir / "timeline.jsonl"
        output_path.write_text(sample_jsonl.read_text(encoding="utf-8"), encoding="utf-8")
        return ScrapeResult(days_scraped=1, days_failed=[], output_path=output_path)

    monkeypatch.setattr("maps_timeline.pipeline.scrape", fake_scrape)
    result = runner.invoke(app, ["run", "--days", "1"])
    assert result.exit_code == 0
    assert "Export run:" in result.stdout
    assert "Google Maps Timeline - summary" in result.stdout


def test_run_command_legacy_raw_out(monkeypatch, tmp_path: Path, sample_jsonl: Path):
    """Infer clean/ from an explicit legacy raw output folder."""
    raw = tmp_path / "raw"
    clean = tmp_path / "clean"
    _fake_scrape(monkeypatch, sample_jsonl)
    result = runner.invoke(
        app, ["run", "--days", "1", "--raw-out", str(raw), "--clean-out", str(clean)]
    )
    assert result.exit_code == 0
    assert (clean / "timeline.csv").exists()


def test_run_command_with_geocode(monkeypatch, tmp_path: Path, sample_jsonl: Path, geocoder_kwargs):
    """Initialize a geocoder in the combined run command."""
    raw = tmp_path / "raw"
    clean = tmp_path / "clean"

    _fake_scrape(monkeypatch, sample_jsonl)
    result = runner.invoke(
        app,
        [
            "run",
            "--days",
            "1",
            "--raw-out",
            str(raw),
            "--clean-out",
            str(clean),
            "--geocode",
            "--nominatim-email",
            "me@example.com",
        ],
    )
    assert result.exit_code == 0
    assert geocoder_kwargs[0]["user_agent"] == "maps-timeline/0.1 (me@example.com)"


def test_run_command_falls_back_to_csv_for_stats(monkeypatch, tmp_path: Path, sample_jsonl: Path):
    """Read CSV in the run summary when parquet is unavailable."""
    raw = tmp_path / "raw"
    clean = tmp_path / "clean"
    csv_path = clean / "timeline.csv"
    clean.mkdir(parents=True, exist_ok=True)
    _fake_scrape(monkeypatch, sample_jsonl)
    monkeypatch.setattr("maps_timeline.merge.build_dataset", lambda *args, **kwargs: csv_path)
    pd.DataFrame(
        [{"day": "2026-06-06", "type": "activity", "title": "Walk", "duration_min": 5.0}]
    ).to_csv(csv_path, index=False)
    result = runner.invoke(
        app,
        ["run", "--days", "1", "--raw-out", str(raw), "--clean-out", str(clean)],
    )
    assert result.exit_code == 0
    assert "Google Maps Timeline - summary" in result.stdout


def test_scrape_command(monkeypatch, tmp_path: Path):
    """Wire scrape through mocked driver and pipeline dependencies."""
    _fake_scrape(
        monkeypatch, tmp_path / "timeline.jsonl", days_scraped=2, days_failed=["2026-06-09"]
    )
    result = runner.invoke(app, ["scrape", "--days", "2", "--out", str(tmp_path)])
    assert result.exit_code == 0
    assert "Done: 2 days" in result.stdout
    assert "failed" in result.stdout


@pytest.mark.usefixtures("isolated_paths")
def test_scrape_command_versioned_run(monkeypatch):
    """Create a versioned export run when scrape --out is omitted."""
    _fake_scrape(monkeypatch)
    result = runner.invoke(app, ["scrape", "--days", "1"])
    assert result.exit_code == 0
    assert "Export run:" in result.stdout


def test_run_command_infers_clean_from_raw_out(monkeypatch, tmp_path: Path, sample_jsonl: Path):
    """Infer clean/ from an explicit raw folder inside a versioned run."""
    run_dir = tmp_path / "runs" / "2026-06-10_120000"
    raw = run_dir / "raw"
    raw.mkdir(parents=True)
    jsonl = raw / "timeline.jsonl"
    jsonl.write_text(sample_jsonl.read_text(encoding="utf-8"), encoding="utf-8")
    _fake_scrape(monkeypatch, jsonl)
    result = runner.invoke(app, ["run", "--days", "1", "--raw-out", str(raw)])
    assert result.exit_code == 0
    assert (run_dir / "clean" / "timeline.csv").exists()


def test_dump_command(tmp_path: Path, monkeypatch):
    """Save a single UI dump through the dump command."""
    monkeypatch.setattr(
        "maps_timeline.device.make_driver",
        lambda **kwargs: MagicMock(dump=lambda: "<hierarchy/>\n", is_healthy=lambda: True),
    )
    out = tmp_path / "screen.xml"
    result = runner.invoke(app, ["dump", "--out", str(out)])
    assert result.exit_code == 0
    assert out.read_text(encoding="utf-8") == "<hierarchy/>\n"


def test_cli_main_entrypoint(monkeypatch):
    """Invoke the script entry point."""
    mock = MagicMock()
    monkeypatch.setattr("maps_timeline.cli.app", mock)
    main()
    mock.assert_called_once()


def test_stats_reads_existing_parquet(tmp_path: Path):
    """Load an existing parquet file without falling back to CSV."""
    df = pd.DataFrame(
        [{"day": "2026-06-06", "type": "activity", "title": "Walk", "duration_min": 5.0}]
    )
    parquet_path = tmp_path / "timeline.parquet"
    df.to_parquet(parquet_path, index=False)
    result = runner.invoke(app, ["stats", "--source", str(parquet_path)])
    assert result.exit_code == 0
    assert "Google Maps Timeline - summary" in result.stdout


def test_package_main_entrypoint(monkeypatch):
    """Invoke the package ``python -m maps_timeline`` entry point."""
    mock = MagicMock()
    monkeypatch.setattr("maps_timeline.cli.main", mock)
    sys.modules.pop("maps_timeline.__main__", None)
    importlib.import_module("maps_timeline.__main__")
    mock.assert_called_once()


def _invalid_export(tmp_path: Path) -> Path:
    """Write a JSON file that is not an on-device Timeline export."""
    path = tmp_path / "Takeout.json"
    path.write_text('{"timelineObjects": []}', encoding="utf-8")
    return path


def test_normalize_command_with_export(sample_jsonl: Path, sample_export: Path, tmp_path: Path):
    """Merge the scrape with an explicit official export."""
    out = tmp_path / "clean"
    result = runner.invoke(
        app,
        [
            "normalize",
            "--jsonl",
            str(sample_jsonl),
            "--export",
            str(sample_export),
            "--out",
            str(out),
        ],
    )
    assert result.exit_code == 0
    assert "scraped entries matched: 1/1" in result.stdout
    assert "source" in pd.read_csv(out / "timeline.csv").columns


def test_normalize_command_rejects_invalid_export(tmp_path: Path):
    """Exit with a clear message when the export format is not supported."""
    result = runner.invoke(
        app, ["normalize", "--export", str(_invalid_export(tmp_path)), "--out", str(tmp_path)]
    )
    assert result.exit_code == 1
    assert "Unsupported Timeline export" in result.stdout


def test_import_command_creates_run(isolated_paths, sample_export: Path):
    """Import the export into a new versioned run and build the dataset."""
    runs_root, marker = isolated_paths
    result = runner.invoke(app, ["import", str(sample_export)])
    assert result.exit_code == 0
    (run_dir,) = runs_root.iterdir()
    assert (run_dir / "raw" / "export.json").is_file()
    assert (run_dir / "clean" / "timeline.csv").is_file()
    assert marker.read_text(encoding="utf-8").strip() == str(run_dir.resolve())
    assert "Named visits: 0/2" in result.stdout


def test_import_command_merges_into_existing_run(
    isolated_paths, sample_export: Path, sample_jsonl: Path
):
    """Attach the export to a run that already has a scrape and merge both."""
    runs_root, marker = isolated_paths
    run_dir = runs_root / "2026-06-10_120000"
    (run_dir / "raw").mkdir(parents=True)
    (run_dir / "raw" / "timeline.jsonl").write_text(
        sample_jsonl.read_text(encoding="utf-8"), encoding="utf-8"
    )
    result = runner.invoke(app, ["import", str(sample_export), "--run", str(run_dir)])
    assert result.exit_code == 0
    assert "scraped entries matched: 1/1" in result.stdout
    assert "Named visits: 2/2" in result.stdout
    assert marker.read_text(encoding="utf-8").strip() == str(run_dir.resolve())


def test_import_command_rejects_invalid_export(isolated_paths, tmp_path: Path):
    """Validate the file before creating any run."""
    runs_root, _marker = isolated_paths
    result = runner.invoke(app, ["import", str(_invalid_export(tmp_path))])
    assert result.exit_code == 1
    assert "Unsupported Timeline export" in result.stdout
    assert not runs_root.exists()


def test_run_command_with_export(
    monkeypatch, tmp_path: Path, sample_jsonl: Path, sample_export: Path
):
    """Copy the export next to the scraped JSONL and merge both."""
    _fake_scrape(monkeypatch, sample_jsonl)
    clean = tmp_path / "clean"
    result = runner.invoke(
        app,
        [
            "run",
            "--days",
            "1",
            "--raw-out",
            str(tmp_path / "raw"),
            "--clean-out",
            str(clean),
            "--export",
            str(sample_export),
        ],
    )
    assert result.exit_code == 0
    assert (sample_jsonl.parent / "export.json").is_file()
    assert "Sources:" in result.stdout
    assert "Named visits:     2/2" in result.stdout


def test_run_command_rejects_invalid_export_before_scraping(monkeypatch, tmp_path: Path):
    """Fail fast on a bad export instead of after a long scrape."""
    make_driver = MagicMock()
    monkeypatch.setattr("maps_timeline.device.make_driver", make_driver)
    result = runner.invoke(
        app,
        ["run", "--raw-out", str(tmp_path / "raw"), "--export", str(_invalid_export(tmp_path))],
    )
    assert result.exit_code == 1
    assert "Unsupported Timeline export" in result.stdout
    make_driver.assert_not_called()


def _fake_scrape_recorder(monkeypatch, output_path: Path, stopped: str | None = None) -> list[dict]:
    """Stub the device and record the arguments the scrape is called with."""
    calls: list[dict] = []
    _fake_device(monkeypatch)

    def fake_scrape(_driver, **kwargs):
        """Record kwargs and pretend the planned days were captured."""
        calls.append(kwargs)
        return ScrapeResult(
            days_scraped=1,
            days_failed=[],
            output_path=output_path,
            days_walked=5,
            stopped=stopped,
        )

    monkeypatch.setattr("maps_timeline.pipeline.scrape", fake_scrape)
    return calls


def test_run_command_defaults_to_three_days(monkeypatch, tmp_path: Path, sample_jsonl: Path):
    """Without --days or --export, walk the historical default of 3 days."""
    calls = _fake_scrape_recorder(monkeypatch, sample_jsonl)
    result = runner.invoke(
        app, ["run", "--raw-out", str(tmp_path / "raw"), "--clean-out", str(tmp_path / "clean")]
    )
    assert result.exit_code == 0
    assert calls[0]["n_days"] == 3
    assert calls[0]["only_days"] is None


@pytest.mark.usefixtures("fixed_today")
def test_run_command_plans_from_export(
    monkeypatch, tmp_path: Path, sample_jsonl: Path, sample_export: Path, isolated_place_names_cache
):
    """With --export and no --days, capture only the planned days and cache new names."""
    calls = _fake_scrape_recorder(monkeypatch, sample_jsonl)
    result = runner.invoke(
        app,
        [
            "run",
            "--raw-out",
            str(tmp_path / "raw"),
            "--clean-out",
            str(tmp_path / "clean"),
            "--export",
            str(sample_export),
        ],
    )
    assert result.exit_code == 0
    assert "[·] Plan: capture 4 of 4 days (back to 2026-06-07) to name 1 places" in result.stdout
    assert "Scraped 1 days (walked 5)" in result.stdout
    assert "Run the same command again" not in result.stdout
    assert calls[0]["only_days"] == RECENT_DAYS  # the cafe shows on 2026-06-07 too
    assert calls[0]["n_days"] == 4
    assert '"place-cafe"' in isolated_place_names_cache.read_text(encoding="utf-8")


@pytest.mark.usefixtures("fixed_today")
def test_run_command_with_export_nothing_to_scrape(
    monkeypatch,
    tmp_path: Path,
    sample_jsonl: Path,
    sample_export: Path,
    isolated_place_names_cache,
):
    """Skip the phone when every place is named and every recent day was captured."""
    isolated_place_names_cache.parent.mkdir(parents=True)
    isolated_place_names_cache.write_text(
        '{"place-cafe": {"title": "Cafe", "address": null}}', encoding="utf-8"
    )
    write_run_scrape(
        paths.RUNS_DIR,
        "2026-06-11_090000",
        *(f'{{"day":"{day.isoformat()}","segments":[]}}' for day in RECENT_DAYS),
    )
    calls = _fake_scrape_recorder(monkeypatch, sample_jsonl)
    result = runner.invoke(
        app, ["run", "--raw-out", str(tmp_path / "raw"), "--export", str(sample_export)]
    )
    assert result.exit_code == 0
    assert "Nothing to scrape" in result.stdout
    assert not calls


@pytest.mark.usefixtures("fixed_today")
def test_run_command_plan_uses_earlier_runs(
    monkeypatch, tmp_path: Path, sample_jsonl: Path, sample_export: Path, isolated_paths
):
    """Names learned by earlier runs (even never merged) and their complete days are reused."""
    runs_root, _marker = isolated_paths
    write_run_scrape(
        runs_root,
        "2026-06-09_120000",
        scraped_visit_day("2026-06-07"),  # names place-cafe; 2026-06-07 is complete
        scraped_visit_day("2026-06-09"),  # captured on its own date: still partial
    )
    calls = _fake_scrape_recorder(monkeypatch, sample_jsonl, stopped="interrupted")
    result = runner.invoke(
        app,
        [
            "run",
            "--raw-out",
            str(tmp_path / "raw"),
            "--clean-out",
            str(tmp_path / "clean"),
            "--export",
            str(sample_export),
        ],
    )
    assert result.exit_code == 0
    assert "to name 0 places" in result.stdout
    assert calls[0]["only_days"] == RECENT_DAYS - {date(2026, 6, 7)}
    assert "Run the same command again to continue" in result.stdout
    assert "scraped days: 3" in result.stdout  # this run's day plus the two earlier ones


@pytest.mark.usefixtures("fixed_today")
def test_scrape_command_plans_from_export(monkeypatch, tmp_path: Path, sample_export: Path):
    """scrape --export plans the walk and copies the export for a later normalize."""
    raw = tmp_path / "raw"
    calls = _fake_scrape_recorder(monkeypatch, raw / "timeline.jsonl", stopped="interrupted")
    result = runner.invoke(app, ["scrape", "--out", str(raw), "--export", str(sample_export)])
    assert result.exit_code == 0
    assert calls[0]["only_days"] == RECENT_DAYS
    assert "Done: 1 days (walked 5)" in result.stdout
    assert "Run the same command again to continue" in result.stdout
    assert (raw / "export.json").is_file()


def test_normalize_command_merges_earlier_runs(
    sample_jsonl: Path, sample_export: Path, tmp_path: Path, isolated_paths
):
    """With an export, normalize also merges the days other runs captured."""
    runs_root, _marker = isolated_paths
    write_run_scrape(runs_root, "2026-06-08_120000", scraped_visit_day("2026-06-07"))
    result = runner.invoke(
        app,
        [
            "normalize",
            "--jsonl",
            str(sample_jsonl),
            "--export",
            str(sample_export),
            "--out",
            str(tmp_path / "clean"),
        ],
    )
    assert result.exit_code == 0
    assert "scraped days: 2, scraped entries matched: 2/2" in result.stdout


@pytest.mark.usefixtures("fixed_today")
def test_run_command_plan_since(
    monkeypatch, tmp_path: Path, sample_jsonl: Path, sample_export: Path
):
    """--since limits the plan to places and days on or after the given date."""
    calls = _fake_scrape_recorder(monkeypatch, sample_jsonl)
    result = runner.invoke(
        app,
        [
            "run",
            "--raw-out",
            str(tmp_path / "raw"),
            "--clean-out",
            str(tmp_path / "clean"),
            "--export",
            str(sample_export),
            "--since",
            "2026-06-09",
        ],
    )
    assert result.exit_code == 0
    assert "to name 0 places" in result.stdout
    assert calls[0]["only_days"] == frozenset({date(2026, 6, 9), TODAY})


@pytest.mark.usefixtures("fixed_today")
def test_run_command_plan_until(
    monkeypatch, tmp_path: Path, sample_jsonl: Path, sample_export: Path
):
    """--until plans only up to that day; the walk still starts from the screen shown."""
    calls = _fake_scrape_recorder(monkeypatch, sample_jsonl)
    result = runner.invoke(
        app,
        [
            "run",
            "--raw-out",
            str(tmp_path / "raw"),
            "--clean-out",
            str(tmp_path / "clean"),
            "--export",
            str(sample_export),
            "--until",
            "2026-06-08",
        ],
    )
    assert result.exit_code == 0
    assert "to name 1 places" in result.stdout
    assert calls[0]["only_days"] == frozenset({date(2026, 6, 7), date(2026, 6, 8)})
    assert calls[0]["n_days"] == 4  # from 2026-06-10 (shown) back to 2026-06-07


def test_run_command_rejects_since_after_until(monkeypatch, tmp_path: Path, sample_export: Path):
    """An empty date window is an input error, reported before touching the phone."""
    calls = _fake_scrape_recorder(monkeypatch, tmp_path / "timeline.jsonl")
    result = runner.invoke(
        app,
        ["run", "--export", str(sample_export), "--since", "2026-06-09", "--until", "2026-06-08"],
    )
    assert result.exit_code == 1
    assert "--since 2026-06-09 is after --until 2026-06-08" in result.stdout
    assert not calls
