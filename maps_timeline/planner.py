"""Plan an export-driven scrape: which days to capture so every place gets a name.

The official export already lists every visit with its Google place ID, but no names.
A name read on one day applies to every visit with the same place ID (see
`merge.py`), so only one day per unnamed place is needed. Because the scraper can only
step back one day at a time, the cost has two parts: how far back it walks, and how
many days it fully captures along the way. The plan minimizes both:

1. Always capture the days the export does not cover (from its last day to the start
   day), unless an earlier run already captured them completely.
2. Target every unnamed place, or with `since` only those visited on or after that day
   (their older visits get the name too). Each place only needs its most recent visit,
   which keeps the walk as short as possible.
3. Within that walk, choose the fewest days that show all of those places (greedy set
   cover, preferring recent days on ties). Every other day is only stepped over.

Days already captured by an earlier run are never planned again. A place still unnamed
after `MAX_ATTEMPTS` of its days were captured (or with no other day left) is one the app
does not show or whose visits do not match (e.g. visits nested inside another one); it is
reported as skipped instead of being looked for again and again.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, timedelta

from .models import OfficialSegment, OfficialSegmentKind

MAX_ATTEMPTS = 2  # captured days on which a place may stay unnamed before it is skipped
TIP_MIN_DAYS = 7  # suggest opening the app on the newest planned day past this many days


@dataclass(frozen=True)
class ScrapePlan:
    """Days to capture and what they are expected to name or fill in."""

    days: frozenset[date]  # days to capture (all on or before the start day)
    places: int  # unnamed places the plan targets
    visits: int  # unnamed visits those places account for
    unnamed_visits: int  # unnamed visits in the export up to the start day
    recent: int = 0  # planned days the export does not cover (from its last day on)
    skipped: int = 0  # unnamed places already looked for on enough captured days

    @property
    def oldest(self) -> date | None:
        """Return the day the walk goes back to, or None when there is nothing to scrape."""
        return min(self.days) if self.days else None

    @property
    def newest(self) -> date | None:
        """Return the most recent planned day, or None when there is nothing to scrape."""
        return max(self.days) if self.days else None

    def walk_days(self, start: date) -> int:
        """Return how many days the scraper visits, from `start` back to the oldest."""
        return (start - self.oldest).days + 1 if self.oldest is not None else 0

    def describe(self, start: date) -> str:
        """Return a counts-only summary of the plan for the console (one line per fact)."""
        lines = []
        if self.oldest is None or self.newest is None:
            lines.append(
                "[·] Nothing to scrape: no unnamed place left to look for and no day newer "
                "than the export to fill in. Run 'import' to rebuild the dataset."
            )
        else:
            recent = (
                f", plus the {self.recent} most recent days (from the export's last day on)"
                if self.recent
                else ""
            )
            lines.append(
                f"[·] Plan: capture {len(self.days)} of {self.walk_days(start)} days "
                f"(back to {self.oldest.isoformat()}) to name {self.places} places "
                f"({self.visits}/{self.unnamed_visits} unnamed visits){recent}."
            )
            ahead = (start - self.newest).days
            if ahead >= TIP_MIN_DAYS:
                lines.append(
                    f"[·] Tip: the newest planned day is {self.newest.isoformat()}. Open the "
                    f"Timeline on that day before starting to skip walking {ahead} newer days."
                )
        if self.skipped:
            lines.append(
                f"[·] Skipping {self.skipped} unnamed places already looked for on captured "
                "days (the app did not show them, or their visits did not match)."
            )
        return "\n".join(lines)


def _min_days(
    places_on: dict[date, set[str]], targets: set[str], seed: frozenset[date] = frozenset()
) -> frozenset[date]:
    """Return few days that, with the `seed` days, show every target place (greedy set cover)."""
    remaining = set(targets)
    for day in seed:
        remaining -= places_on.get(day, set())
    pool = {day: places & remaining for day, places in places_on.items() if places & remaining}
    chosen: set[date] = set(seed)
    while remaining:
        best = max(pool, key=lambda day: (len(pool[day] & remaining), day))
        chosen.add(best)
        remaining -= pool.pop(best)
    return frozenset(chosen)


def _unnamed_visits(
    official: list[OfficialSegment], start: date, known: set[str]
) -> dict[date, list[str]]:
    """Group the place IDs of unnamed visits up to `start` by the day they start on."""
    by_day: dict[date, list[str]] = {}
    for seg in official:
        if seg.kind is not OfficialSegmentKind.VISIT or not seg.place_id:
            continue
        day = seg.start.date()
        if seg.place_id not in known and day <= start:
            by_day.setdefault(day, []).append(seg.place_id)
    return by_day


def _uncovered_days(
    official: list[OfficialSegment], start: date, captured: frozenset[date]
) -> frozenset[date]:
    """Return the days from the export's last day to `start` that no run captured completely."""
    if not official:
        return frozenset()
    last = max(seg.end.date() for seg in official)
    days = {last + timedelta(days=offset) for offset in range((start - last).days + 1)}
    return frozenset(days - captured)


def _open_days(by_day: dict[date, list[str]], captured: frozenset[date]) -> dict[date, set[str]]:
    """Return the days not captured yet, with the places still worth looking for on them."""
    attempts = Counter(
        place_id
        for day, place_ids in by_day.items()
        if day in captured
        for place_id in set(place_ids)
    )
    return {
        day: {place_id for place_id in place_ids if attempts[place_id] < MAX_ATTEMPTS}
        for day, place_ids in by_day.items()
        if day not in captured
    }


def _latest_days(open_days: dict[date, set[str]]) -> dict[str, date]:
    """Map each place to the most recent open day that shows it."""
    latest: dict[str, date] = {}
    for day, place_ids in open_days.items():
        for place_id in place_ids:
            latest[place_id] = max(day, latest.get(place_id, day))
    return latest


def plan_scrape(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    official: list[OfficialSegment],
    start: date,
    known: Iterable[str] = (),
    since: date | None = None,
    captured: frozenset[date] = frozenset(),
) -> ScrapePlan:
    """Plan which days to capture to name the places of unnamed visits (since `since`).

    Without `since`, every unnamed place is targeted, however far back. `captured` holds
    the days earlier runs already captured completely: they are not planned again, and
    each one counts as an attempt for the unnamed places it shows.
    """
    by_day = _unnamed_visits(official, start, set(known))
    weight = Counter(place_id for place_ids in by_day.values() for place_id in place_ids)
    open_days = _open_days(by_day, captured)
    latest = _latest_days(open_days)
    first = since or date.min
    chosen = {place_id for place_id, day in latest.items() if day >= first}
    uncovered = frozenset(day for day in _uncovered_days(official, start, captured) if day >= first)
    oldest = min((latest[p] for p in chosen), default=start)
    window = {day: place_ids for day, place_ids in open_days.items() if day >= oldest}
    return ScrapePlan(
        days=_min_days(window, chosen, seed=uncovered),
        places=len(chosen),
        visits=sum(weight[place_id] for place_id in chosen),
        unnamed_visits=sum(weight.values()),
        recent=len(uncovered),
        skipped=len(weight) - len(latest),
    )
