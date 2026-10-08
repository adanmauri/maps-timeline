"""Offline tests for the export-driven scrape planner."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from maps_timeline.models import OfficialSegment, OfficialSegmentKind
from maps_timeline.planner import MAX_ATTEMPTS, ScrapePlan, plan_scrape

TZ = timezone(timedelta(hours=-3))
START = date(2026, 6, 30)


def _visit(days_ago: int, place_id: str | None) -> OfficialSegment:
    """Build a one-hour visit `days_ago` days before the start day."""
    day = START - timedelta(days=days_ago)
    start = datetime(day.year, day.month, day.day, 10, tzinfo=TZ)
    return OfficialSegment(
        kind=OfficialSegmentKind.VISIT,
        start=start,
        end=start + timedelta(hours=1),
        place_id=place_id,
    )


def _ago(days: int) -> date:
    """Return the date `days` before the start day."""
    return START - timedelta(days=days)


def _export() -> list[OfficialSegment]:
    """Visits: p1 on -1/-10, p2 on -5, p3 on -3/-5/-20, a known place, and noise."""
    trip_start = datetime(2026, 6, 29, 9, tzinfo=TZ)
    return [
        _visit(1, "p1"),
        _visit(10, "p1"),
        _visit(5, "p2"),
        _visit(3, "p3"),
        _visit(5, "p3"),
        _visit(20, "p3"),
        _visit(2, "home"),
        _visit(4, None),
        _visit(-1, "future"),  # after the start day: not reachable walking back
        OfficialSegment(
            kind=OfficialSegmentKind.ACTIVITY,
            start=trip_start,
            end=trip_start + timedelta(minutes=10),
        ),
    ]


def test_plan_covers_every_unnamed_place_with_few_days():
    """Walk back to the most recent visit of each place; capture a minimal set of days."""
    plan = plan_scrape(_export(), START, known={"home"})
    assert plan.days == frozenset({_ago(1), _ago(5)})  # day -5 shows both p2 and p3
    assert (plan.oldest, plan.newest) == (_ago(5), _ago(1))
    assert (plan.places, plan.visits, plan.unnamed_visits) == (3, 6, 6)
    assert (plan.recent, plan.skipped) == (0, 0)  # the export reaches past the start day
    assert plan.walk_days(START) == 6


def test_plan_since_walks_less():
    """Only target places visited on or after `since`; their older visits are named too."""
    plan = plan_scrape(_export(), START, known={"home"}, since=_ago(2))
    assert plan.days == frozenset({_ago(1)})
    assert (plan.places, plan.visits, plan.unnamed_visits) == (1, 2, 6)
    assert plan.walk_days(START) == 2


def test_plan_since_also_limits_days_the_export_does_not_cover():
    """Days the export does not reach are captured only from `since` on."""
    plan = plan_scrape([_visit(2, "p1")], START, since=_ago(0))
    assert plan.days == frozenset({_ago(0)})
    assert (plan.places, plan.visits, plan.recent) == (0, 0, 1)


def test_plan_nothing_to_scrape():
    """Return an empty plan when every place is already named."""
    plan = plan_scrape(_export(), START, known={"p1", "p2", "p3", "home"})
    assert plan == ScrapePlan(frozenset(), 0, 0, 0)
    assert (plan.oldest, plan.newest) == (None, None)
    assert plan.walk_days(START) == 0
    assert "Nothing to scrape" in plan.describe(START)


def test_plan_describe_counts_only():
    """Describe the plan with counts and ISO dates."""
    plan = plan_scrape(_export(), START, known={"home"})
    assert plan.describe(START) == (
        "[·] Plan: capture 2 of 6 days (back to 2026-06-25) to name 3 places "
        "(6/6 unnamed visits)."
    )


def test_plan_never_revisits_captured_days():
    """Captured days are not planned again; their places are looked for on other days."""
    plan = plan_scrape(_export(), START, known={"home"}, captured=frozenset({_ago(1)}))
    assert plan.days == frozenset({_ago(5), _ago(10)})  # p1 again, on its other day
    assert (plan.places, plan.skipped) == (3, 0)


def test_plan_skips_places_after_max_attempts():
    """Stop looking for a place once enough of its days were captured without a name."""
    captured = frozenset({_ago(1), _ago(10)})  # both p1 days, p1 still unnamed
    assert MAX_ATTEMPTS == 2
    plan = plan_scrape(_export(), START, known={"home"}, captured=captured)
    assert plan.days == frozenset({_ago(5)})
    assert (plan.places, plan.visits, plan.unnamed_visits, plan.skipped) == (2, 4, 6, 1)
    assert "Skipping 1 unnamed places already looked for" in plan.describe(START)


def test_plan_skips_places_without_days_left():
    """A place whose only day was captured is skipped after a single attempt."""
    plan = plan_scrape(_export(), START, known={"home", "p1", "p3"}, captured=frozenset({_ago(5)}))
    assert plan.days == frozenset()
    assert plan.skipped == 1
    assert plan.describe(START).splitlines()[1].startswith("[·] Skipping 1 unnamed places")


def test_plan_fills_days_the_export_does_not_cover():
    """Capture every day from the export's last day on, unless a run captured it already."""
    official = [_visit(2, "p1")]
    plan = plan_scrape(official, START, captured=frozenset({_ago(1)}))
    assert plan.days == frozenset({_ago(2), _ago(0)})  # p1 is named on a day captured anyway
    assert (plan.places, plan.visits, plan.recent) == (1, 1, 2)
    assert plan.describe(START) == (
        "[·] Plan: capture 2 of 3 days (back to 2026-06-28) to name 1 places "
        "(1/1 unnamed visits), plus the 2 most recent days (from the export's last day on)."
    )


def test_plan_with_empty_export():
    """Nothing to plan without segments."""
    assert plan_scrape([], START).days == frozenset()


def test_plan_tip_when_the_newest_planned_day_is_far_back():
    """Suggest opening the app on the newest planned day to skip a long walk."""
    official = [_visit(30, "p9"), _visit(-1, "future")]
    plan = plan_scrape(official, START, known={"future"})
    assert plan.describe(START).splitlines()[1] == (
        "[·] Tip: the newest planned day is 2026-05-31. Open the Timeline on that day "
        "before starting to skip walking 30 newer days."
    )
