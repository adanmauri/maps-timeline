"""Domain models for a Timeline day and its segments.

The scraper stores *raw* data (text exactly as it appears on screen).
Normalization to numeric types / ISO dates lives in `normalize.py`, so the JSONL
can be reprocessed without re-scanning the phone.
"""

from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class SegmentType(StrEnum):
    """Kind of Timeline segment parsed from a content-desc string."""

    PLACE_VISIT = "place_visit"  # place name + address in content-desc
    ACTIVITY = "activity"  # transport mode with distance and duration
    UNCONFIRMED_VISIT = "unconfirmed_visit"  # unconfirmed visit prompt
    UNKNOWN_VISIT = "unknown_visit"  # unknown visit label
    MISSING_TRANSIT = "missing_transit"  # missing transit mode segment


class TimeAnchor(StrEnum):
    """How a segment's time is anchored in the UI."""

    RANGE = "range"  # time range in content-desc
    DEPARTURE = "departure"  # departure time anchor (first point of the day)
    ARRIVAL = "arrival"  # arrival time anchor (last point of the day)
    ALL_DAY = "all_day"  # whole-day visit with no specific clock times


class Segment(BaseModel):
    """One parsed Timeline entry (visit, trip leg, or unresolved segment)."""

    type: SegmentType
    title: str | None = None  # place name or transport mode
    address: str | None = None
    time_anchor: TimeAnchor | None = None
    start_time: str | None = None  # raw, e.g. "4:49 PM"
    end_time: str | None = None
    duration_text: str | None = None  # "10 min" / "1 h 15 min"
    distance_text: str | None = None  # "2,4 km"
    confirmed: bool | None = None  # False for unconfirmed visits
    needs_user_action: bool = False  # True if Google could not resolve the segment
    raw_desc: str = ""  # full content-desc, for traceability/debug


class DaySummary(BaseModel):
    """On-screen totals shown at the top of a Timeline day."""

    total_distance_text: str | None = None  # "18 km"
    total_duration_text: str | None = None  # "1 h 15 min"
    visit_count: int | None = None  # 5


class DayTimeline(BaseModel):
    """All segments and metadata for one Timeline day."""

    day: date
    header_text: str | None = None  # "Sat Jun 6, 2026" exactly as the app showed it
    summary: DaySummary = Field(default_factory=DaySummary)
    segments: list[Segment] = Field(default_factory=list)
    scraped_at: datetime = Field(default_factory=datetime.now)

    @property
    def place_visits(self) -> int:
        """Count place-like visits the way Google totals them in the day summary."""
        visit_types = (
            SegmentType.PLACE_VISIT,
            SegmentType.UNCONFIRMED_VISIT,
            SegmentType.UNKNOWN_VISIT,
        )
        return sum(1 for s in self.segments if s.type in visit_types)

    def summary_matches(self) -> bool | None:
        """Cross-check: does the parsed visit count match the on-screen summary?"""
        if self.summary.visit_count is None:
            return None
        return self.place_visits == self.summary.visit_count


class OfficialSegmentKind(StrEnum):
    """Kind of semantic segment read from the official on-device Timeline export."""

    VISIT = "visit"  # stay at a place (placeId + coordinates, no name)
    ACTIVITY = "activity"  # movement between two points


class OfficialSegment(BaseModel):
    """One visit or activity from the official on-device Timeline export (Timeline.json)."""

    kind: OfficialSegmentKind
    start: datetime  # timezone-aware, exactly as exported
    end: datetime
    probability: float | None = None
    place_id: str | None = None  # visits: Google place ID
    semantic_type: str | None = None  # visits: UNKNOWN, INFERRED_HOME, INFERRED_WORK, ...
    hierarchy_level: int | None = None  # visits: 0 = top level, 1 = nested inside another visit
    lat: float | None = None  # visits: place location
    lon: float | None = None
    activity_type: str | None = None  # activities: WALKING, IN_PASSENGER_VEHICLE, ...
    distance_m: float | None = None  # activities: travelled distance
    start_lat: float | None = None  # activities: start point
    start_lon: float | None = None
    end_lat: float | None = None  # activities: end point
    end_lon: float | None = None
