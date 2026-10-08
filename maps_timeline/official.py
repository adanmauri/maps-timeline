"""Parse the official on-device Timeline export (``Timeline.json``) from Android.

Since Timeline moved to on-device storage, Android can export it from Settings →
Location → Location services → Timeline → "Export Timeline data". The file has
precise coordinates and Google place IDs but **no place names or addresses**, which
is exactly what the UI scraper captures; `merge.py` joins both sources.

Only the visits and activities in ``semanticSegments`` are read. ``timelinePath``
points, ``timelineMemory`` trip summaries, ``rawSignals`` (GPS fixes, Wi-Fi scans)
and ``userLocationProfile`` are ignored.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from .models import OfficialSegment, OfficialSegmentKind

# "-34.6037°, -58.3816°" (Android export) or "geo:-34.6037,-58.3816" (other exports).
_LAT_LNG_RE = re.compile(r"^\s*(?:geo:)?\s*(-?\d+(?:\.\d+)?)°?\s*,\s*(-?\d+(?:\.\d+)?)°?\s*$")


def parse_lat_lng(text: str | None) -> tuple[float, float] | None:
    """Parse '-34.6°, -58.4°' or 'geo:-34.6,-58.4' into (lat, lon); None if unparseable."""
    if not text:
        return None
    m = _LAT_LNG_RE.match(text)
    if not m:
        return None
    return float(m.group(1)), float(m.group(2))


def _lat_lng_dict(node: Any) -> tuple[float, float] | None:
    """Read coordinates from a ``{"latLng": "..."}`` node."""
    return parse_lat_lng(node.get("latLng")) if isinstance(node, dict) else None


def _visit(raw: dict[str, Any], start: datetime, end: datetime) -> OfficialSegment:
    """Build a visit segment from one ``semanticSegments`` entry."""
    visit = raw["visit"]
    candidate = visit.get("topCandidate") or {}
    coords = _lat_lng_dict(candidate.get("placeLocation"))
    return OfficialSegment(
        kind=OfficialSegmentKind.VISIT,
        start=start,
        end=end,
        probability=visit.get("probability"),
        place_id=candidate.get("placeId"),
        semantic_type=candidate.get("semanticType"),
        hierarchy_level=visit.get("hierarchyLevel"),
        lat=coords[0] if coords else None,
        lon=coords[1] if coords else None,
    )


def _activity(raw: dict[str, Any], start: datetime, end: datetime) -> OfficialSegment:
    """Build an activity segment from one ``semanticSegments`` entry."""
    activity = raw["activity"]
    candidate = activity.get("topCandidate") or {}
    origin = _lat_lng_dict(activity.get("start"))
    destination = _lat_lng_dict(activity.get("end"))
    return OfficialSegment(
        kind=OfficialSegmentKind.ACTIVITY,
        start=start,
        end=end,
        probability=activity.get("probability"),
        activity_type=candidate.get("type"),
        distance_m=activity.get("distanceMeters"),
        start_lat=origin[0] if origin else None,
        start_lon=origin[1] if origin else None,
        end_lat=destination[0] if destination else None,
        end_lon=destination[1] if destination else None,
    )


def _segment(raw: Any) -> OfficialSegment | None:
    """Convert one ``semanticSegments`` entry into a segment, or None when it is not relevant."""
    if not isinstance(raw, dict) or "startTime" not in raw or "endTime" not in raw:
        return None
    if "visit" not in raw and "activity" not in raw:
        return None
    start = datetime.fromisoformat(raw["startTime"])
    end = datetime.fromisoformat(raw["endTime"])
    if start.tzinfo is None or end.tzinfo is None:
        raise ValueError(
            f"Timeline export timestamps must include a UTC offset: {raw['startTime']}"
        )
    if "visit" in raw:
        return _visit(raw, start, end)
    return _activity(raw, start, end)


def parse_official_export(data: Any) -> list[OfficialSegment]:
    """Return the visits and activities of a decoded export, sorted by start time."""
    segments = data.get("semanticSegments") if isinstance(data, dict) else None
    if not isinstance(segments, list):
        raise ValueError(
            "Unsupported Timeline export: expected a top-level 'semanticSegments' list "
            "(the Android on-device export from Settings → Location → Timeline)."
        )
    parsed = [seg for raw in segments if (seg := _segment(raw)) is not None]
    return sorted(parsed, key=lambda seg: seg.start)


def load_official_export(path: Path) -> list[OfficialSegment]:
    """Read and parse an official Timeline export file."""
    with path.open(encoding="utf-8") as fh:
        return parse_official_export(json.load(fh))
