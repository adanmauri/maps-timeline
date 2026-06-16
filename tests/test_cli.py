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

from maps_timeline.cli import app, main, read_header_text_safe
from maps_timeline.pipeline import ScrapeResult
from tests.conftest import button_xml, day_dump_xml, text_xml

runner = CliRunner()


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


def test_normalize_with_geocode_flag(sample_jsonl, tmp_path: Path, monkeypatch):
    """Initialize a geocoder when --geocode is passed."""
    created: list[object] = []

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
    assert created


def test_run_command(monkeypatch, tmp_path: Path, sample_jsonl: Path):
    """Run scrape, normalize, and stats in one invocation."""
    raw = tmp_path / "raw"
    clean = tmp_path / "clean"
    monkeypatch.setattr(
        "maps_timeline.device.make_driver",
        lambda **kwargs: MagicMock(dump=lambda: "<hierarchy/>", is_healthy=lambda: True),
    )
    monkeypatch.setattr(
        "maps_timeline.pipeline.scrape",
        lambda *args, **kwargs: ScrapeResult(
            days_scraped=1,
            days_failed=[],
            output_path=sample_jsonl,
        ),
    )
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
    monkeypatch.setattr(
        "maps_timeline.device.make_driver",
        lambda **kwargs: MagicMock(dump=lambda: "<hierarchy/>", is_healthy=lambda: True),
    )

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
    monkeypatch.setattr(
        "maps_timeline.device.make_driver",
        lambda **kwargs: MagicMock(dump=lambda: "<hierarchy/>", is_healthy=lambda: True),
    )
    monkeypatch.setattr(
        "maps_timeline.pipeline.scrape",
        lambda *args, **kwargs: ScrapeResult(
            days_scraped=1,
            days_failed=[],
            output_path=sample_jsonl,
        ),
    )
    result = runner.invoke(
        app, ["run", "--days", "1", "--raw-out", str(raw), "--clean-out", str(clean)]
    )
    assert result.exit_code == 0
    assert (clean / "timeline.csv").exists()


def test_run_command_with_geocode(monkeypatch, tmp_path: Path, sample_jsonl: Path):
    """Initialize a geocoder in the combined run command."""
    raw = tmp_path / "raw"
    clean = tmp_path / "clean"
    created: list[object] = []

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
    monkeypatch.setattr(
        "maps_timeline.device.make_driver",
        lambda **kwargs: MagicMock(dump=lambda: "<hierarchy/>", is_healthy=lambda: True),
    )
    monkeypatch.setattr(
        "maps_timeline.pipeline.scrape",
        lambda *args, **kwargs: ScrapeResult(
            days_scraped=1,
            days_failed=[],
            output_path=sample_jsonl,
        ),
    )
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
    assert created


def test_run_command_falls_back_to_csv_for_stats(monkeypatch, tmp_path: Path, sample_jsonl: Path):
    """Read CSV in the run summary when parquet is unavailable."""
    raw = tmp_path / "raw"
    clean = tmp_path / "clean"
    csv_path = clean / "timeline.csv"
    clean.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(
        "maps_timeline.device.make_driver",
        lambda **kwargs: MagicMock(dump=lambda: "<hierarchy/>", is_healthy=lambda: True),
    )
    monkeypatch.setattr(
        "maps_timeline.pipeline.scrape",
        lambda *args, **kwargs: ScrapeResult(
            days_scraped=1,
            days_failed=[],
            output_path=sample_jsonl,
        ),
    )
    monkeypatch.setattr("maps_timeline.normalize.normalize", lambda *args, **kwargs: csv_path)
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
    monkeypatch.setattr(
        "maps_timeline.device.make_driver",
        lambda **kwargs: MagicMock(dump=lambda: "<hierarchy/>", is_healthy=lambda: True),
    )
    monkeypatch.setattr(
        "maps_timeline.pipeline.scrape",
        lambda *args, **kwargs: ScrapeResult(
            days_scraped=2,
            days_failed=["2026-06-09"],
            output_path=tmp_path / "timeline.jsonl",
        ),
    )
    result = runner.invoke(app, ["scrape", "--days", "2", "--out", str(tmp_path)])
    assert result.exit_code == 0
    assert "Done: 2 days" in result.stdout
    assert "failed" in result.stdout


@pytest.mark.usefixtures("isolated_paths")
def test_scrape_command_versioned_run(monkeypatch):
    """Create a versioned export run when scrape --out is omitted."""
    monkeypatch.setattr(
        "maps_timeline.device.make_driver",
        lambda **kwargs: MagicMock(dump=lambda: "<hierarchy/>", is_healthy=lambda: True),
    )
    monkeypatch.setattr(
        "maps_timeline.pipeline.scrape",
        lambda *args, **kwargs: ScrapeResult(
            days_scraped=1,
            days_failed=[],
            output_path=kwargs["out_dir"] / "timeline.jsonl",
        ),
    )
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
    monkeypatch.setattr(
        "maps_timeline.device.make_driver",
        lambda **kwargs: MagicMock(dump=lambda: "<hierarchy/>", is_healthy=lambda: True),
    )
    monkeypatch.setattr(
        "maps_timeline.pipeline.scrape",
        lambda *args, **kwargs: ScrapeResult(
            days_scraped=1,
            days_failed=[],
            output_path=jsonl,
        ),
    )
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
