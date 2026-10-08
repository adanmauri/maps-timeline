"""Offline tests for merging the scraped Timeline with the official export."""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, cast

import pandas as pd
import pytest

from maps_timeline.geocode import NominatimGeocoder
from maps_timeline.merge import (
    COLUMNS,
    Match,
    MergeOutcome,
    ScrapedEntry,
    align,
    build_dataset,
    known_place_names,
    learn_titles,
    load_place_names,
    merge_report,
    merge_rows,
    offset_minutes,
    overlap_score,
    save_place_names,
    scraped_interval,
)
from maps_timeline.models import OfficialSegment, OfficialSegmentKind
from maps_timeline.official import load_official_export, parse_official_export
from tests.conftest import official_export_payload, scraped_visit_day, write_run_scrape

TZ = timezone(timedelta(hours=-3))
DAY = date(2026, 6, 6)


def _at(day: date, hour: int, minute: int = 0) -> datetime:
    """Return a naive local datetime on `day`."""
    return datetime(day.year, day.month, day.day, hour, minute)


def _visit(start: datetime, end: datetime, place_id: str = "p1", **extra: Any) -> OfficialSegment:
    """Build an official visit in the test timezone."""
    return OfficialSegment(
        kind=OfficialSegmentKind.VISIT,
        start=start.replace(tzinfo=TZ),
        end=end.replace(tzinfo=TZ),
        place_id=place_id,
        lat=-34.6,
        lon=-58.4,
        **extra,
    )


def _activity(
    start: datetime, end: datetime, activity_type: str | None = "WALKING", **extra: Any
) -> OfficialSegment:
    """Build an official activity in the test timezone."""
    return OfficialSegment(
        kind=OfficialSegmentKind.ACTIVITY,
        start=start.replace(tzinfo=TZ),
        end=end.replace(tzinfo=TZ),
        activity_type=activity_type,
        **extra,
    )


def _entry(day: date = DAY, **segment: Any) -> ScrapedEntry:
    """Build a scraped entry from raw segment fields."""
    return ScrapedEntry(day, segment)


def test_scraped_interval_by_anchor():
    """Turn each UI time anchor into a local wall-clock interval."""
    midnight = _at(DAY, 0)
    next_midnight = midnight + timedelta(days=1)
    assert scraped_interval(_entry(time_anchor="all_day")) == (midnight, next_midnight)
    assert scraped_interval(_entry(time_anchor="departure", start_time="8:30 AM")) == (
        midnight,
        _at(DAY, 8, 30),
    )
    assert scraped_interval(_entry(time_anchor="arrival", end_time="10:00 PM")) == (
        _at(DAY, 22),
        next_midnight,
    )
    assert scraped_interval(
        _entry(time_anchor="range", start_time="4:49 PM", end_time="4:59 PM")
    ) == (_at(DAY, 16, 49), _at(DAY, 16, 59))


def test_scraped_interval_range_crossing_midnight():
    """Push the end to the next day when a range wraps around midnight."""
    interval = scraped_interval(_entry(start_time="11:00 PM", end_time="1:00 AM"))
    assert interval == (_at(DAY, 23), _at(DAY, 1) + timedelta(days=1))


def test_scraped_interval_without_times():
    """Return None when the entry has no usable times."""
    assert scraped_interval(_entry(time_anchor="departure")) is None
    assert scraped_interval(_entry(time_anchor="arrival")) is None
    assert scraped_interval(_entry(type="activity", start_time="4:49 PM")) is None


def test_overlap_score():
    """Compute intersection over union, including degenerate intervals."""
    a = (_at(DAY, 10), _at(DAY, 12))
    assert overlap_score(a, a) == 1.0
    assert overlap_score(a, (_at(DAY, 11), _at(DAY, 13))) == pytest.approx(1 / 3)
    assert overlap_score(a, (_at(DAY, 13), _at(DAY, 14))) == 0.0
    instant = (_at(DAY, 10), _at(DAY, 10))
    assert overlap_score(instant, instant) == 1.0


def test_align_pairs_compatible_kinds():
    """Match visits with visits and activities with activities by time overlap."""
    official = [
        _visit(_at(DAY, 9), _at(DAY, 10)),
        _activity(_at(DAY, 10), _at(DAY, 10, 20)),
    ]
    scraped = [
        _entry(type="activity", start_time="10:00 AM", end_time="10:20 AM"),
        _entry(type="place_visit", start_time="9:00 AM", end_time="10:00 AM"),
        _entry(type="missing_transit", start_time="9:00 AM", end_time="10:00 AM"),
        _entry(type="mystery", start_time="9:00 AM", end_time="10:00 AM"),
        _entry(type="unknown_visit"),  # no times
    ]
    matches = align(scraped, official)
    assert matches == [Match(0, 1, 1.0), Match(1, 0, 1.0)]


def test_align_crossing_midnight_matches_once_per_day():
    """A visit across midnight absorbs the arrival entry and the next day's departure."""
    next_day = DAY + timedelta(days=1)
    official = [_visit(_at(DAY, 22), _at(next_day, 8))]
    scraped = [
        _entry(DAY, type="place_visit", time_anchor="arrival", end_time="10:00 PM"),
        _entry(next_day, type="place_visit", time_anchor="departure", start_time="8:00 AM"),
    ]
    assert [(m.scraped, m.official) for m in align(scraped, official)] == [(0, 0), (1, 0)]


def test_align_is_one_to_one_per_day_and_respects_threshold():
    """Keep only the best entry per official segment and day; drop weak overlaps."""
    official = [_visit(_at(DAY, 9), _at(DAY, 11))]
    scraped = [
        _entry(type="place_visit", start_time="9:30 AM", end_time="11:00 AM"),  # 0.75
        _entry(type="place_visit", start_time="9:00 AM", end_time="11:00 AM"),  # 1.0
        _entry(type="place_visit", start_time="10:50 AM", end_time="11:00 AM"),  # weak
    ]
    matches = align(scraped, official)
    assert [(m.scraped, m.official) for m in matches] == [(1, 0)]
    assert align(scraped[:1], official, min_score=0.9) == []


def test_align_truncates_official_seconds():
    """Compare at minute precision, like the app's clock times."""
    official = [_activity(_at(DAY, 10, 0) + timedelta(seconds=59), _at(DAY, 10, 5))]
    scraped = [_entry(type="activity", start_time="10:00 AM", end_time="10:05 AM")]
    assert align(scraped, official)[0].score == 1.0


def test_learn_titles_picks_most_common():
    """Return the most frequent value per key and skip empty keys."""
    learned = learn_titles(
        [
            ("p1", ("Cafe", "Main 1")),
            ("p1", ("Cafe", "Main 1")),
            ("p1", ("Café", None)),
            (None, ("Ignored", None)),
            ("", ("Ignored", None)),
        ]
    )
    assert learned == {"p1": ("Cafe", "Main 1")}


def test_offset_minutes():
    """Report UTC offsets in minutes, or None for naive datetimes."""
    assert offset_minutes(_at(DAY, 10).replace(tzinfo=TZ)) == -180
    assert offset_minutes(_at(DAY, 10)) is None


def _days(*segments: dict[str, Any], day: date = DAY) -> list[dict[str, Any]]:
    """Wrap raw segments into one raw JSONL day dict."""
    return [{"day": day.isoformat(), "segments": list(segments)}]


def test_merge_rows_matched_and_propagated():
    """Combine fields from both sources and reuse names on unscraped days."""
    next_day = DAY + timedelta(days=1)
    official = [
        _visit(_at(DAY, 9), _at(DAY, 10), place_id="p1", probability=0.9),
        _activity(_at(DAY, 10), _at(DAY, 10, 20), distance_m=1500.0),
        _visit(_at(next_day, 9), _at(next_day, 10), place_id="p1"),
        _activity(_at(next_day, 10), _at(next_day, 10, 20)),
    ]
    days = _days(
        {
            "type": "place_visit",
            "title": "Cafe",
            "address": "Main 1",
            "start_time": "9:00 AM",
            "end_time": "10:00 AM",
            "confirmed": True,
        },
        {
            "type": "activity",
            "title": "A pie",
            "start_time": "10:00 AM",
            "end_time": "10:20 AM",
            "distance_text": "2 km",
        },
    )
    outcome = merge_rows(days, official)
    assert (outcome.scraped, outcome.matched) == (2, 2)
    assert all(tuple(row) == COLUMNS for row in outcome.rows)

    visit, walk, propagated, walk_label = outcome.rows
    assert visit["source"] == "both"
    assert visit["title_source"] == "scrape"
    assert (visit["title"], visit["address"]) == ("Cafe", "Main 1")
    assert (visit["lat"], visit["lon"]) == (-34.6, -58.4)
    assert visit["confirmed"] is True
    assert visit["start_iso"] == "2026-06-06T09:00:00"
    assert visit["duration_min"] == 60.0
    assert visit["tz_offset_min"] == -180
    assert visit["match_score"] == 1.0
    assert walk["distance_km"] == 1.5  # official distance wins over the UI text
    assert walk["activity_type"] == "WALKING"

    assert propagated["source"] == "export"
    assert (propagated["title"], propagated["address"]) == ("Cafe", "Main 1")
    assert propagated["title_source"] == "place_id"
    assert propagated["match_score"] is None
    assert propagated["needs_user_action"] is False
    assert walk_label["title"] == "A pie"
    assert walk_label["title_source"] == "activity_type"


def test_merge_rows_fallbacks_without_names():
    """Leave visits unnamed, label activities by type, and keep scrape-only entries."""
    official = [
        _visit(_at(DAY, 9), _at(DAY, 10), place_id="p2"),
        _activity(_at(DAY, 10), _at(DAY, 10, 20), activity_type="IN_BUS"),
        _activity(_at(DAY, 11), _at(DAY, 11, 20), activity_type=None),
        _activity(_at(DAY, 12), _at(DAY, 12, 30), activity_type=None),
    ]
    days = _days(
        {"type": "unknown_visit", "start_time": "6:00 AM", "end_time": "7:00 AM"},
        {"type": "activity", "title": "En autobús"},  # no times -> scrape only
        {"type": "unknown_visit", "start_time": "9:00 AM", "end_time": "10:00 AM"},
        {
            "type": "missing_transit",
            "start_time": "12:00 PM",
            "end_time": "12:30 PM",
            "distance_text": "3 km",
        },
    )
    outcome = merge_rows(days, official)
    by_start = {row["start_iso"]: row for row in outcome.rows}

    unnamed = by_start["2026-06-06T09:00:00"]
    assert unnamed["type"] == "unknown_visit"
    assert unnamed["title"] is None
    assert unnamed["title_source"] is None

    assert by_start["2026-06-06T10:00:00"]["title"] == "IN_BUS"
    assert by_start["2026-06-06T10:00:00"]["title_source"] == "export"
    assert by_start["2026-06-06T11:00:00"]["title"] is None

    transit = by_start["2026-06-06T12:00:00"]
    assert transit["type"] == "missing_transit"
    assert transit["distance_km"] == 3.0  # no official distance: fall back to the UI text

    scrape_only = [row for row in outcome.rows if row["source"] == "scrape"]
    assert [row["title_source"] for row in scrape_only] == ["scrape", None]
    assert scrape_only[0]["start_iso"] is None  # entries without times sort first in their day
    assert scrape_only[1]["start_iso"] == "2026-06-06T06:00:00"


def test_merge_report_counts_only():
    """Summarize merge coverage without leaking names."""
    outcome = merge_rows(
        _days(
            {
                "type": "place_visit",
                "title": "Cafe",
                "start_time": "9:00 AM",
                "end_time": "10:00 AM",
            }
        ),
        [
            _visit(_at(DAY, 9), _at(DAY, 10)),
            _visit(_at(DAY, 11), _at(DAY, 12)),
            _activity(_at(DAY, 10), _at(DAY, 10, 30)),
        ],
    )
    report = merge_report(outcome)
    assert "2 visits, 1 activities" in report
    assert "scraped days: 1, scraped entries matched: 1/1" in report
    assert "Named visits: 2/2 (scrape: 1, propagated by place ID: 1)" in report
    assert "Cafe" not in report


def test_merge_report_ignores_scrape_only_rows():
    """Count only rows that come from the official export."""
    outcome = MergeOutcome(
        rows=[{"source": "scrape", "type": "place_visit", "title": "X", "title_source": "scrape"}],
        scraped=1,
        matched=0,
    )
    assert "0 visits, 0 activities" in merge_report(outcome)


def test_build_dataset_scrape_only(sample_jsonl: Path, tmp_path: Path):
    """Without an export, keep the original normalize output."""
    csv_path = build_dataset(sample_jsonl, None, tmp_path / "out")
    assert "source" not in pd.read_csv(csv_path).columns


def test_build_dataset_requires_an_input(tmp_path: Path):
    """Refuse to build a dataset from nothing."""
    with pytest.raises(ValueError, match="Nothing to normalize"):
        build_dataset(None, None, tmp_path)


def test_build_dataset_export_only(sample_export: Path, tmp_path: Path, capsys):
    """Build a dataset from the official export alone."""
    csv_path = build_dataset(None, sample_export, tmp_path / "out")
    df = pd.read_csv(csv_path)
    assert set(df["source"]) == {"export"}
    assert len(df) == 3
    assert "scraped entries matched: 0/0" in capsys.readouterr().out


def test_build_dataset_merged(sample_jsonl: Path, sample_export: Path, tmp_path: Path):
    """Merge the sample scrape with the sample export and propagate the place name."""
    csv_path = build_dataset(sample_jsonl, sample_export, tmp_path / "out")
    df = pd.read_csv(csv_path)
    assert list(df["source"]) == ["both", "export", "export"]
    assert list(df["title"]) == ["Cafe", "WALKING", "Cafe"]
    assert (tmp_path / "out" / "timeline.parquet").exists()


def test_build_dataset_geocodes_only_rows_without_coordinates(sample_export: Path, tmp_path: Path):
    """Skip Nominatim for rows that already have official coordinates."""
    queried: list[str] = []

    class FakeGeocoder:
        """Record geocoding requests."""

        def geocode(self, address: str) -> tuple[float, float]:
            """Return fixed coordinates and log the address."""
            queried.append(address)
            return (1.0, 2.0)

        def close(self) -> None:
            """No-op close hook for pylint public-method parity."""

    jsonl = tmp_path / "timeline.jsonl"
    jsonl.write_text(
        '{"day":"2026-06-08","segments":[{"type":"place_visit","title":"Bar",'
        '"address":"Side 2","start_time":"9:00 PM","end_time":"10:00 PM"}]}\n',
        encoding="utf-8",
    )
    geocoder = cast(NominatimGeocoder, FakeGeocoder())
    build_dataset(jsonl, sample_export, tmp_path / "out", geocoder=geocoder)
    df = pd.read_csv(tmp_path / "out" / "timeline.csv")
    assert queried == ["Side 2"]
    assert df.loc[df["source"] == "scrape", "lat"].tolist() == [1.0]


def test_parse_and_merge_sample_payload():
    """The shared synthetic payload parses into the segments the merge tests expect."""
    segments = parse_official_export(official_export_payload())
    assert [seg.place_id for seg in segments if seg.kind is OfficialSegmentKind.VISIT] == [
        "place-cafe",
        "place-cafe",
    ]


def test_place_names_cache_round_trip(tmp_path: Path):
    """Save and load the place-name cache; a missing file reads as empty."""
    cache = tmp_path / "cache" / "places.json"
    assert load_place_names(cache) == {}
    save_place_names(cache, {"p2": ("Bar", None), "p1": ("Cafe", "Main 1")})
    assert load_place_names(cache) == {"p1": ("Cafe", "Main 1"), "p2": ("Bar", None)}
    assert cache.read_text(encoding="utf-8").index('"p1"') < cache.read_text().index('"p2"')


def test_merge_rows_known_names_fill_gaps_and_lose_to_fresh_ones():
    """Use cached names for unscraped places; names learned now take precedence."""
    official = [
        _visit(_at(DAY, 9), _at(DAY, 10), place_id="p1"),
        _visit(_at(DAY, 11), _at(DAY, 12), place_id="p2"),
    ]
    days = _days(
        {"type": "place_visit", "title": "Cafe", "start_time": "9:00 AM", "end_time": "10:00 AM"}
    )
    known = {"p1": ("Old cafe", None), "p2": ("Bar", "Side 2")}
    outcome = merge_rows(days, official, known)
    assert [row["title"] for row in outcome.rows] == ["Cafe", "Bar"]
    assert outcome.rows[1]["title_source"] == "place_id"
    assert outcome.names == {"p1": ("Cafe", None), "p2": ("Bar", "Side 2")}


def test_build_dataset_updates_names_cache(sample_jsonl: Path, sample_export: Path, tmp_path: Path):
    """Learn names on one run and reuse them on a later export-only run."""
    cache = tmp_path / "places.json"
    build_dataset(sample_jsonl, sample_export, tmp_path / "first", names_cache=cache)
    assert load_place_names(cache) == {"place-cafe": ("Cafe", "Main 1")}

    csv_path = build_dataset(None, sample_export, tmp_path / "second", names_cache=cache)
    df = pd.read_csv(csv_path)
    visits = df[df["type"] == "place_visit"]
    assert list(visits["title"]) == ["Cafe", "Cafe"]
    assert set(visits["title_source"]) == {"place_id"}


def test_known_place_names_learns_from_scraped_days(sample_jsonl: Path, sample_export: Path):
    """Learn names from scraped days matched to the export, keeping other known ones."""
    days = [json.loads(line) for line in sample_jsonl.read_text(encoding="utf-8").splitlines()]
    names = known_place_names(days, load_official_export(sample_export), {"p0": ("Home", None)})
    assert names == {"p0": ("Home", None), "place-cafe": ("Cafe", "Main 1")}


def test_build_dataset_merges_earlier_runs(
    sample_jsonl: Path, sample_export: Path, tmp_path: Path, capsys
):
    """Days captured by earlier runs are merged too; the current scrape wins on overlap."""
    earlier = write_run_scrape(
        tmp_path / "runs",
        "2026-06-08_120000",
        scraped_visit_day("2026-06-07"),
        scraped_visit_day("2026-06-06", "1:00 AM", "2:00 AM"),  # replaced by the current scrape
    )
    csv_path = build_dataset(sample_jsonl, sample_export, tmp_path / "out", earlier=[earlier])
    df = pd.read_csv(csv_path)
    assert list(df["source"]) == ["both", "export", "both"]
    assert "scraped days: 2, scraped entries matched: 2/2" in capsys.readouterr().out
