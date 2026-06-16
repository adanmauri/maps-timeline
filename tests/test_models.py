"""Tests for domain models."""

from __future__ import annotations

from datetime import date

from maps_timeline.models import DaySummary, DayTimeline, Segment, SegmentType


def test_place_visits_counts_confirmed_and_unconfirmed():
    """Count both confirmed and unconfirmed place visits."""
    timeline = DayTimeline(
        day=date(2026, 6, 6),
        segments=[
            Segment(type=SegmentType.PLACE_VISIT, title="A"),
            Segment(type=SegmentType.UNCONFIRMED_VISIT, title="B"),
            Segment(type=SegmentType.ACTIVITY, title="C"),
        ],
    )
    assert timeline.place_visits == 2


def test_summary_matches_when_counts_align():
    """Return True when parsed visits match the on-screen summary."""
    timeline = DayTimeline(
        day=date(2026, 6, 6),
        summary=DaySummary(visit_count=1),
        segments=[Segment(type=SegmentType.PLACE_VISIT, title="A")],
    )
    assert timeline.summary_matches() is True


def test_summary_matches_none_when_summary_missing():
    """Return None when the UI did not expose a visit count."""
    timeline = DayTimeline(day=date(2026, 6, 6), segments=[])
    assert timeline.summary_matches() is None


def test_summary_matches_false_on_mismatch():
    """Return False when parsed visits disagree with the summary."""
    timeline = DayTimeline(
        day=date(2026, 6, 6),
        summary=DaySummary(visit_count=3),
        segments=[Segment(type=SegmentType.PLACE_VISIT, title="A")],
    )
    assert timeline.summary_matches() is False
