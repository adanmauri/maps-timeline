"""Merge the scraped Timeline with the official on-device export into one dataset.

The two sources complement each other:

- The **scrape** (`timeline.jsonl`) has what the app shows: place names, addresses,
  transport-mode labels, and whether Google still needs the user to confirm a visit.
- The **official export** (`Timeline.json`, see `official.py`) has precise coordinates,
  Google place IDs, UTC offsets and distances for the whole history, but no names.

Alignment works per scraped day: each scraped entry is paired with the official
segment of a compatible kind (visit or activity) whose local wall-clock interval
overlaps it best, measured as intersection over union (at least `MIN_MATCH_SCORE`).
A visit that crosses midnight shows up on two scraped days (arrival / departure
anchors), so one official segment may absorb one scraped entry per day.

Names learned from matched visits are then propagated to every other visit with the
same place ID, including days that were never scraped; transport labels are
propagated the same way by activity type. Learned place names are kept in a small
cache (place ID -> name, address) so later runs reuse them and `planner.py` only
schedules days for places that are still unnamed.

With an export, the scrape side is the whole scrape history (`history.py`): every day
captured by any run, the latest capture of each day winning.
"""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .history import load_history
from .models import OfficialSegment, OfficialSegmentKind
from .normalize import normalize, parse_distance_km, scrape_row, to_iso, write_dataset
from .official import load_official_export

if TYPE_CHECKING:
    from .geocode import NominatimGeocoder

MIN_MATCH_SCORE = 0.5

_VISIT_TYPES = frozenset({"place_visit", "unconfirmed_visit", "unknown_visit"})
_ACTIVITY_TYPES = frozenset({"activity", "missing_transit"})

COLUMNS = (
    "day",
    "type",
    "title",
    "address",
    "start_iso",
    "end_iso",
    "duration_min",
    "distance_km",
    "confirmed",
    "needs_user_action",
    "lat",
    "lon",
    "start_lat",
    "start_lon",
    "end_lat",
    "end_lon",
    "place_id",
    "semantic_type",
    "probability",
    "hierarchy_level",
    "activity_type",
    "tz_offset_min",
    "source",
    "title_source",
    "match_score",
)

Interval = tuple[datetime, datetime]
Learned = tuple[str, str | None]  # (title, address)


@dataclass(frozen=True)
class ScrapedEntry:
    """One raw scraped segment together with the day it was shown on."""

    day: date
    segment: dict[str, Any]


@dataclass(frozen=True)
class Match:
    """A scraped entry paired with an official segment, with its overlap score."""

    scraped: int  # index into the scraped entries
    official: int  # index into the official segments
    score: float


@dataclass(frozen=True)
class MergeOutcome:
    """Merged rows plus counters for the console report."""

    rows: list[dict[str, Any]]
    scraped: int  # scraped entries considered
    matched: int  # scraped entries paired with an official segment
    names: dict[str, Learned] = field(default_factory=dict)  # place ID -> (title, address)
    days: int = 0  # scraped days considered


def _kind(seg_type: str | None) -> OfficialSegmentKind | None:
    """Map a scraped segment type to the official segment kind it can match."""
    if seg_type in _VISIT_TYPES:
        return OfficialSegmentKind.VISIT
    if seg_type in _ACTIVITY_TYPES:
        return OfficialSegmentKind.ACTIVITY
    return None


def _clock(day: date, text: str | None) -> datetime | None:
    """Combine a day with a UI clock time ('4:59 PM') into a naive local datetime."""
    iso = to_iso(day.isoformat(), text)
    return datetime.fromisoformat(iso) if iso else None


def scraped_interval(entry: ScrapedEntry) -> Interval | None:
    """Return the local wall-clock interval a scraped entry covers, or None without times."""
    seg = entry.segment
    day_start = datetime.combine(entry.day, time.min)
    day_end = day_start + timedelta(days=1)
    start = _clock(entry.day, seg.get("start_time"))
    end = _clock(entry.day, seg.get("end_time"))
    anchor = seg.get("time_anchor")
    if anchor == "all_day":
        return day_start, day_end
    if anchor == "departure":  # first entry of the day: from midnight until leaving
        return (day_start, start) if start is not None else None
    if anchor == "arrival":  # last entry of the day: from arriving until midnight
        return (end, day_end) if end is not None else None
    if start is None or end is None:
        return None
    if end < start:  # range that crosses midnight
        end += timedelta(days=1)
    return start, end


def official_interval(seg: OfficialSegment) -> Interval:
    """Return the segment's local wall-clock interval, truncated to minutes like the app."""
    return (
        seg.start.replace(tzinfo=None, second=0, microsecond=0),
        seg.end.replace(tzinfo=None, second=0, microsecond=0),
    )


def overlap_score(a: Interval, b: Interval) -> float:
    """Intersection over union of two intervals (1.0 for identical zero-length ones)."""
    intersection = (min(a[1], b[1]) - max(a[0], b[0])).total_seconds()
    union = (max(a[1], b[1]) - min(a[0], b[0])).total_seconds()
    if union <= 0:
        return 1.0
    return max(intersection, 0.0) / union


def _index_by_day(intervals: list[Interval]) -> dict[date, list[int]]:
    """Map each local date to the official segments that touch it."""
    index: dict[date, list[int]] = {}
    for i, (start, end) in enumerate(intervals):
        day = start.date()
        while day <= end.date():
            index.setdefault(day, []).append(i)
            day += timedelta(days=1)
    return index


def _window(entry: ScrapedEntry, interval: Interval) -> Interval:
    """Return the span official segments are clipped to: the day, widened to fit the entry."""
    day_start = datetime.combine(entry.day, time.min)
    return min(day_start, interval[0]), max(day_start + timedelta(days=1), interval[1])


def _candidates(
    scraped: list[ScrapedEntry], official: list[OfficialSegment], min_score: float
) -> list[Match]:
    """Score every compatible (scraped, official) pair that overlaps on the scraped day."""
    intervals = [official_interval(seg) for seg in official]
    index = _index_by_day(intervals)
    candidates: list[Match] = []
    for s_idx, entry in enumerate(scraped):
        kind = _kind(entry.segment.get("type"))
        interval = scraped_interval(entry)
        if kind is None or interval is None:
            continue
        window = _window(entry, interval)
        for o_idx in index.get(entry.day, []):
            if official[o_idx].kind is not kind:
                continue
            o_start, o_end = intervals[o_idx]
            score = overlap_score(interval, (max(o_start, window[0]), min(o_end, window[1])))
            if score >= min_score:
                candidates.append(Match(s_idx, o_idx, score))
    return candidates


def align(
    scraped: list[ScrapedEntry],
    official: list[OfficialSegment],
    min_score: float = MIN_MATCH_SCORE,
) -> list[Match]:
    """Pair scraped entries with official segments, best overlap first, one per segment per day."""
    candidates = sorted(
        _candidates(scraped, official, min_score),
        key=lambda m: (-m.score, m.scraped, m.official),
    )
    used_scraped: set[int] = set()
    used_official: set[tuple[int, date]] = set()
    matches: list[Match] = []
    for match in candidates:
        slot = (match.official, scraped[match.scraped].day)
        if match.scraped in used_scraped or slot in used_official:
            continue
        used_scraped.add(match.scraped)
        used_official.add(slot)
        matches.append(match)
    return sorted(matches, key=lambda m: m.scraped)


def learn_titles(pairs: Iterable[tuple[str | None, Learned]]) -> dict[str, Learned]:
    """Return the most frequent (title, address) per key, ignoring empty keys."""
    counts: dict[str, Counter[Learned]] = {}
    for key, value in pairs:
        if key:
            counts.setdefault(key, Counter())[value] += 1
    return {key: counter.most_common(1)[0][0] for key, counter in counts.items()}


def offset_minutes(moment: datetime) -> int | None:
    """Return the UTC offset of an aware datetime in minutes (None when naive)."""
    offset = moment.utcoffset()
    return None if offset is None else int(offset.total_seconds() // 60)


def _official_row(
    seg: OfficialSegment,
    matched: list[tuple[ScrapedEntry, float]],
    names: dict[str, Learned],
    labels: dict[str, Learned],
) -> dict[str, Any]:
    """Build one clean row from an official segment and the scraped entries matched to it."""
    primary = matched[0][0].segment if matched else {}
    is_visit = seg.kind is OfficialSegmentKind.VISIT
    title, address = primary.get("title"), primary.get("address")
    title_source = "scrape" if title else None
    if not title:
        learned = names.get(seg.place_id or "") if is_visit else labels.get(seg.activity_type or "")
        if learned:
            title, address = learned[0], address or learned[1]
            title_source = "place_id" if is_visit else "activity_type"
        elif not is_visit and seg.activity_type:
            title, title_source = seg.activity_type, "export"
    distance_km = (
        seg.distance_m / 1000
        if seg.distance_m is not None
        else parse_distance_km(primary.get("distance_text"))
    )
    return {
        "day": seg.start.date().isoformat(),
        "type": primary.get("type") or ("place_visit" if is_visit else "activity"),
        "title": title,
        "address": address,
        "start_iso": seg.start.replace(tzinfo=None).isoformat(),
        "end_iso": seg.end.replace(tzinfo=None).isoformat(),
        "duration_min": round((seg.end - seg.start).total_seconds() / 60, 1),
        "distance_km": distance_km,
        "confirmed": primary.get("confirmed"),
        "needs_user_action": bool(primary.get("needs_user_action", False)),
        "lat": seg.lat,
        "lon": seg.lon,
        "start_lat": seg.start_lat,
        "start_lon": seg.start_lon,
        "end_lat": seg.end_lat,
        "end_lon": seg.end_lon,
        "place_id": seg.place_id,
        "semantic_type": seg.semantic_type,
        "probability": seg.probability,
        "hierarchy_level": seg.hierarchy_level,
        "activity_type": seg.activity_type,
        "tz_offset_min": offset_minutes(seg.start),
        "source": "both" if matched else "export",
        "title_source": title_source,
        "match_score": round(max(score for _, score in matched), 3) if matched else None,
    }


def _scrape_only_row(entry: ScrapedEntry) -> dict[str, Any]:
    """Build one clean row for a scraped entry that matched no official segment."""
    row = scrape_row(entry.day.isoformat(), entry.segment)
    row["source"] = "scrape"
    row["title_source"] = "scrape" if row["title"] else None
    return {column: row.get(column) for column in COLUMNS}


def load_place_names(path: Path) -> dict[str, Learned]:
    """Read the place-name cache (place ID -> title, address); empty when missing."""
    if not path.is_file():
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    return {place_id: (entry["title"], entry.get("address")) for place_id, entry in raw.items()}


def save_place_names(path: Path, names: dict[str, Learned]) -> None:
    """Write the place-name cache, sorted by place ID for stable diffs."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        place_id: {"title": title, "address": address}
        for place_id, (title, address) in sorted(names.items())
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _scraped_entries(days: list[dict[str, Any]]) -> list[ScrapedEntry]:
    """Flatten raw JSONL day objects into scraped entries tagged with their day."""
    return [
        ScrapedEntry(date.fromisoformat(str(day_obj["day"])), seg)
        for day_obj in days
        for seg in day_obj.get("segments", [])
    ]


def _place_names(
    pairs: list[tuple[OfficialSegment, dict[str, Any]]], known: dict[str, Learned] | None
) -> dict[str, Learned]:
    """Combine `known` names with those learned from matched visits (learned ones win)."""
    return {
        **(known or {}),
        **learn_titles(
            (seg.place_id, (s["title"], s.get("address")))
            for seg, s in pairs
            if s.get("type") == "place_visit" and s.get("title")
        ),
    }


def known_place_names(
    days: list[dict[str, Any]],
    official: list[OfficialSegment],
    known: dict[str, Learned] | None = None,
) -> dict[str, Learned]:
    """Return the place names the scraped days teach about the export, plus `known` ones."""
    scraped = _scraped_entries(days)
    matches = align(scraped, official)
    return _place_names(
        [(official[m.official], scraped[m.scraped].segment) for m in matches], known
    )


def learned_so_far(
    official: list[OfficialSegment], sources: Iterable[Path], names_cache: Path | None
) -> tuple[dict[str, Learned], frozenset[date]]:
    """Return the place names known before a scrape and the days already captured completely.

    Names come from the cache and from every earlier scrape (`sources`) matched to `official`.
    """
    history = load_history(sources)
    cache = load_place_names(names_cache) if names_cache is not None else None
    return known_place_names(history.days, official, cache), history.complete


def merge_rows(
    days: list[dict[str, Any]],
    official: list[OfficialSegment],
    known: dict[str, Learned] | None = None,
) -> MergeOutcome:
    """Merge scraped days (raw JSONL dicts) with official segments into clean rows.

    `known` place names (e.g. from earlier runs) fill in places this scrape did not see;
    names learned now take precedence.
    """
    scraped = _scraped_entries(days)
    matches = align(scraped, official)

    by_official: dict[int, list[tuple[ScrapedEntry, float]]] = {}
    for match in matches:
        by_official.setdefault(match.official, []).append((scraped[match.scraped], match.score))

    pairs = [(official[m.official], scraped[m.scraped].segment) for m in matches]
    names = _place_names(pairs, known)
    labels = learn_titles(
        (seg.activity_type, (s["title"], None))
        for seg, s in pairs
        if s.get("type") == "activity" and s.get("title")
    )

    rows = [
        _official_row(seg, by_official.get(i, []), names, labels) for i, seg in enumerate(official)
    ]
    matched_idx = {m.scraped for m in matches}
    rows += [_scrape_only_row(e) for i, e in enumerate(scraped) if i not in matched_idx]
    rows.sort(key=lambda r: (r["day"], r["start_iso"] or ""))
    return MergeOutcome(
        rows=rows, scraped=len(scraped), matched=len(matches), names=names, days=len(days)
    )


def merge_report(outcome: MergeOutcome) -> str:
    """Summarize a merge with counts only (no place names or coordinates)."""
    official_rows = [r for r in outcome.rows if r["source"] != "scrape"]
    visits = [r for r in official_rows if _kind(r["type"]) is OfficialSegmentKind.VISIT]
    named = Counter(r["title_source"] for r in visits if r["title"])
    activities = len(official_rows) - len(visits)
    return (
        f"[·] Official export: {len(visits)} visits, {activities} activities | "
        f"scraped days: {outcome.days}, "
        f"scraped entries matched: {outcome.matched}/{outcome.scraped}\n"
        f"[·] Named visits: {sum(named.values())}/{len(visits)} "
        f"(scrape: {named['scrape']}, propagated by place ID: {named['place_id']})"
    )


def build_dataset(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    jsonl_path: Path | None,
    export_path: Path | None,
    out_dir: Path,
    geocoder: NominatimGeocoder | None = None,
    names_cache: Path | None = None,
    earlier: Iterable[Path] = (),
) -> Path:
    """Write the clean dataset from the scrape, the official export, or both merged.

    With an export, the days in `earlier` raw JSONL files (older runs, oldest first) are
    merged too; `jsonl_path` wins for days captured more than once. With `names_cache`,
    place names from earlier runs are reused and the cache is updated with the names
    learned now.
    """
    if export_path is None:
        if jsonl_path is None:
            raise ValueError(
                "Nothing to normalize: pass a scraped JSONL, an official export, or both."
            )
        return normalize(jsonl_path, out_dir, geocoder)
    sources = [*earlier, *([jsonl_path] if jsonl_path is not None else [])]
    known = load_place_names(names_cache) if names_cache is not None else None
    outcome = merge_rows(load_history(sources).days, load_official_export(export_path), known)
    if names_cache is not None:
        save_place_names(names_cache, outcome.names)
    print(merge_report(outcome))
    return write_dataset(outcome.rows, out_dir, geocoder)
