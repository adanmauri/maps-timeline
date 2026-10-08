"""Tests for dataset summary rendering."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from maps_timeline.stats import _activity_modes, format_minutes, load_dataframe, render, summarize


def test_format_minutes_branches():
    """Cover all formatting branches for minute totals."""
    assert format_minutes(None) == "0 min"
    assert format_minutes(45) == "45 min"
    assert format_minutes(120) == "2 h"
    assert format_minutes(150) == "2 h 30 min"


def test_summarize_empty_dataframe():
    """Return a default Summary for an empty DataFrame."""
    summary = summarize(pd.DataFrame())
    assert summary.total_segments == 0
    assert render(summary).startswith("No data to summarize")


def test_summarize_and_render_full_dataset():
    """Compute metrics and render a non-empty report."""
    df = pd.DataFrame(
        [
            {
                "day": "2026-06-06",
                "type": "place_visit",
                "title": "Cafe",
                "address": "Main 1",
                "distance_km": 5.0,
                "duration_min": 30.0,
                "needs_user_action": False,
                "lat": -34.0,
            },
            {
                "day": "2026-06-06",
                "type": "place_visit",
                "title": "Cafe",
                "address": "Main 2",
                "distance_km": 3.0,
                "duration_min": 15.0,
                "needs_user_action": True,
                "lat": None,
            },
            {
                "day": "2026-06-07",
                "type": "activity",
                "title": "Walk",
                "distance_km": 1.0,
                "duration_min": 10.0,
            },
        ]
    )
    summary = summarize(df, top=1)
    text = render(summary)
    assert "Google Maps Timeline - summary" in text
    assert "Busiest day" in text
    assert "Travel by mode:" in text
    assert "Walk" in text
    assert "Geocoded:" in text
    assert "Most visited places:" in text
    assert "Cafe" in text


def test_load_dataframe_csv_and_parquet(tmp_path: Path):
    """Load datasets from CSV and Parquet paths."""
    df = pd.DataFrame([{"day": "2026-06-06", "type": "activity"}])
    csv_path = tmp_path / "timeline.csv"
    parquet_path = tmp_path / "timeline.parquet"
    df.to_csv(csv_path, index=False)
    df.to_parquet(parquet_path, index=False)

    pd.testing.assert_frame_equal(load_dataframe(csv_path), df)
    pd.testing.assert_frame_equal(load_dataframe(parquet_path), df)


def test_summarize_minimal_columns():
    """Summarize datasets that only contain the core columns."""
    df = pd.DataFrame([{"day": "2026-06-06", "type": "activity", "title": "Walk"}])
    summary = summarize(df)
    assert summary.needs_action == 0
    assert summary.busiest_day is None
    assert summary.geocoded is None
    assert not summary.top_places


def test_render_without_optional_sections():
    """Render a summary that omits busiest day, geocoding, and top places."""
    summary = summarize(
        pd.DataFrame(
            [{"day": "2026-06-06", "type": "activity", "title": "Walk", "duration_min": 0.0}]
        )
    )
    text = render(summary)
    assert "Busiest day" not in text
    assert "Geocoded:" not in text
    assert "Most visited places:" not in text


def test_summarize_activity_modes():
    """Aggregate distance and duration by activity title."""
    df = pd.DataFrame(
        [
            {
                "day": "2026-06-06",
                "type": "activity",
                "title": "A pie",
                "distance_km": 0.7,
                "duration_min": 10.0,
            },
            {
                "day": "2026-06-07",
                "type": "activity",
                "title": "A pie",
                "distance_km": 0.9,
                "duration_min": 12.0,
            },
            {
                "day": "2026-06-07",
                "type": "activity",
                "title": "En automóvil",
                "distance_km": 10.0,
                "duration_min": 20.0,
            },
        ]
    )
    summary = summarize(df)
    assert summary.by_mode == [("En automóvil", 10.0, 20.0), ("A pie", 1.6, 22.0)]


def test_activity_modes_without_title_column():
    """Return no mode totals when the dataset lacks a title column."""
    assert _activity_modes(pd.DataFrame([{"day": "2026-06-06", "type": "activity"}])) == []


def test_summarize_zero_distance_busiest_day():
    """Skip busiest-day metrics when all daily distances are zero."""
    df = pd.DataFrame(
        [
            {
                "day": "2026-06-06",
                "type": "activity",
                "title": "Walk",
                "distance_km": 0.0,
                "duration_min": 1.0,
            }
        ]
    )
    assert summarize(df).busiest_day is None


def test_load_dataframe_missing_file(tmp_path: Path):
    """Raise FileNotFoundError when the dataset path does not exist."""
    with pytest.raises(FileNotFoundError):
        load_dataframe(tmp_path / "missing.csv")


def test_summarize_merged_dataset():
    """Report sources and named visits, and keep stay time out of travel time."""
    df = pd.DataFrame(
        [
            {
                "day": "2026-06-06",
                "type": "place_visit",
                "title": "Cafe",
                "address": None,
                "duration_min": 60.0,
                "lat": -34.6,
                "source": "both",
            },
            {
                "day": "2026-06-07",
                "type": "place_visit",
                "title": None,
                "address": None,
                "duration_min": 30.0,
                "lat": -34.6,
                "source": "export",
            },
            {
                "day": "2026-06-07",
                "type": "activity",
                "title": "WALKING",
                "address": None,
                "duration_min": 15.0,
                "lat": None,
                "source": "export",
            },
        ]
    )
    summary = summarize(df)
    assert summary.total_travel_min == 15.0
    assert summary.geocoded is None
    assert summary.sources == {"both": 1, "export": 2}
    assert summary.named_visits == (1, 2)
    text = render(summary)
    assert "Sources:          both 1 | export 2" in text
    assert "Named visits:     1/2" in text
    assert "Geocoded:" not in text
