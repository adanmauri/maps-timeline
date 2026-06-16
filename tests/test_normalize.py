"""Offline tests for the normalization helpers (pure functions)."""

from __future__ import annotations

from datetime import date
from typing import cast

import pandas as pd

from maps_timeline.geocode import NominatimGeocoder
from maps_timeline.navigator import resolve_header_date
from maps_timeline.normalize import normalize, parse_distance_km, parse_duration_minutes, to_iso


def test_parse_duration_minutes():
    """Convert Spanish duration strings into total minutes."""
    assert parse_duration_minutes("42 min") == 42
    assert parse_duration_minutes("1 h 15 min") == 75
    assert parse_duration_minutes("2 h") == 120
    assert parse_duration_minutes("1\xa0h 5\xa0min") == 65  # non-breaking spaces from the app
    assert parse_duration_minutes(None) is None


def test_parse_distance_km():
    """Convert Spanish distance strings into kilometers."""
    assert parse_distance_km("2,4 km") == 2.4
    assert parse_distance_km("14 km") == 14.0
    assert parse_distance_km("850 m") == 0.85
    assert parse_distance_km(None) is None


def test_to_iso():
    """Combine a day string and a 12-hour time into ISO local datetime text."""
    assert to_iso("2026-06-06", "4:59 PM") == "2026-06-06T16:59:00"
    assert to_iso("2026-06-06", None) is None
    assert to_iso("2026-06-06", "not a time") is None


def test_resolve_header_date():
    """Resolve relative and absolute English header strings to dates."""
    today = date(2026, 6, 10)
    assert resolve_header_date("Today", today) == today
    assert resolve_header_date("Yesterday", today) == date(2026, 6, 9)
    assert resolve_header_date("Sat Jun 6, 2026", today) == date(2026, 6, 6)
    assert resolve_header_date("garbage", today) is None


def test_parse_duration_without_digits_returns_none():
    """Return None when the duration string has no recognizable units."""
    assert parse_duration_minutes("soon") is None


def test_parse_distance_invalid_returns_none():
    """Return None when the distance string does not match the parser."""
    assert parse_distance_km("far") is None


def test_normalize_writes_csv_and_parquet(sample_jsonl, tmp_path):
    """Flatten a JSONL file into CSV and Parquet outputs."""
    csv_path = normalize(sample_jsonl, tmp_path)
    assert csv_path.exists()
    assert (tmp_path / "timeline.parquet").exists()


def test_normalize_skips_blank_lines(tmp_path):
    """Ignore blank lines in the JSONL input."""
    jsonl = tmp_path / "timeline.jsonl"
    jsonl.write_text(
        "\n\n"
        '{"day":"2026-06-06","segments":[{"type":"activity","title":"Walk",'
        '"start_time":"4:00 PM","distance_text":"1 km","duration_text":"5 min"}]}\n',
        encoding="utf-8",
    )
    normalize(jsonl, tmp_path / "out")
    assert (tmp_path / "out" / "timeline.csv").exists()


def test_normalize_with_geocoder(sample_jsonl, tmp_path):
    """Attach lat/lon columns when a geocoder is provided."""

    class StubGeocoder:
        """Minimal geocoder stub for normalize integration tests."""

        def geocode(self, address: str | None) -> tuple[float | None, float | None]:
            """Return fixed coordinates for any non-empty address."""
            return (-34.0, -58.0) if address else (None, None)

        def close(self) -> None:
            """No-op hook so the stub matches richer geocoder shapes."""

    normalize(sample_jsonl, tmp_path, geocoder=cast(NominatimGeocoder, StubGeocoder()))
    df = pd.read_csv(tmp_path / "timeline.csv")
    assert df.loc[0, "lat"] == -34.0
