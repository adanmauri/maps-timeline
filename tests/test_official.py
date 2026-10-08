"""Offline tests for parsing the official on-device Timeline export."""

from __future__ import annotations

from pathlib import Path

import pytest

from maps_timeline.models import OfficialSegmentKind
from maps_timeline.official import load_official_export, parse_lat_lng, parse_official_export
from tests.conftest import official_export_payload


def test_parse_lat_lng_formats():
    """Accept the Android degree format and the geo: URI format."""
    assert parse_lat_lng("-34.6037°, -58.3816°") == (-34.6037, -58.3816)
    assert parse_lat_lng("geo:-34.6,-58.4") == (-34.6, -58.4)
    assert parse_lat_lng("12°, 3°") == (12.0, 3.0)


def test_parse_lat_lng_invalid():
    """Return None for missing or unparseable coordinates."""
    assert parse_lat_lng(None) is None
    assert parse_lat_lng("") is None
    assert parse_lat_lng("somewhere") is None


def test_parse_official_export_reads_visits_and_activities():
    """Keep visits and activities, ignore timeline paths, and sort by start."""
    segments = parse_official_export(official_export_payload())
    assert [seg.kind for seg in segments] == [
        OfficialSegmentKind.VISIT,
        OfficialSegmentKind.ACTIVITY,
        OfficialSegmentKind.VISIT,
    ]
    visit, activity, _ = segments
    assert visit.place_id == "place-cafe"
    assert visit.semantic_type == "UNKNOWN"
    assert visit.hierarchy_level == 0
    assert visit.probability == 0.9
    assert (visit.lat, visit.lon) == (-34.6037, -58.3816)
    assert visit.start.utcoffset() is not None
    assert activity.activity_type == "WALKING"
    assert activity.distance_m == 800.0
    assert (activity.start_lat, activity.start_lon) == (-34.6037, -58.3816)
    assert (activity.end_lat, activity.end_lon) == (-34.61, -58.39)


def test_parse_official_export_sorts_across_offsets():
    """Sort by absolute time even when segments use different UTC offsets."""
    data = {
        "semanticSegments": [
            {
                "startTime": "2026-06-06T12:00:00+02:00",  # 10:00 UTC
                "endTime": "2026-06-06T13:00:00+02:00",
                "visit": {"topCandidate": {"placeId": "later"}},
            },
            {
                "startTime": "2026-06-06T06:00:00-03:00",  # 09:00 UTC
                "endTime": "2026-06-06T07:00:00-03:00",
                "visit": {"topCandidate": {"placeId": "earlier"}},
            },
        ]
    }
    assert [seg.place_id for seg in parse_official_export(data)] == ["earlier", "later"]


def test_parse_official_export_tolerates_sparse_entries():
    """Handle missing candidates/coordinates and skip malformed or irrelevant entries."""
    data = {
        "semanticSegments": [
            "not a segment",
            {"visit": {}},  # no times
            {"startTime": "2026-06-06T10:00:00Z", "endTime": "2026-06-06T11:00:00Z"},
            {
                "startTime": "2026-06-06T10:00:00Z",
                "endTime": "2026-06-06T11:00:00Z",
                "visit": {"topCandidate": {"placeLocation": "-34.6°, -58.4°"}},
            },
            {
                "startTime": "2026-06-06T11:00:00Z",
                "endTime": "2026-06-06T12:00:00Z",
                "activity": {},
            },
        ]
    }
    visit, activity = parse_official_export(data)
    assert visit.place_id is None
    assert visit.lat is None  # placeLocation must be an object with latLng
    assert activity.activity_type is None
    assert activity.start_lat is None
    assert activity.end_lat is None


def test_parse_official_export_requires_offsets():
    """Reject naive timestamps: local wall-clock times need their UTC offset."""
    data = {
        "semanticSegments": [
            {
                "startTime": "2026-06-06T10:00:00",
                "endTime": "2026-06-06T11:00:00",
                "visit": {},
            }
        ]
    }
    with pytest.raises(ValueError, match="UTC offset"):
        parse_official_export(data)


@pytest.mark.parametrize("data", [[], {"timelineObjects": []}, {"semanticSegments": {}}])
def test_parse_official_export_rejects_unknown_formats(data):
    """Fail clearly for Takeout-style or malformed files."""
    with pytest.raises(ValueError, match="semanticSegments"):
        parse_official_export(data)


def test_load_official_export(sample_export: Path):
    """Read and parse an export file from disk."""
    assert len(load_official_export(sample_export)) == 3
