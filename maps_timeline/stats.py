"""Console summary of the clean dataset (data/clean).

Reads the normalized CSV/Parquet and computes a human-readable overview:
date range, totals (distance and travel time), most visited places, and how
many entries still need user action. Pure functions operate on a DataFrame so
they can be unit-tested without touching the filesystem.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

_PLACE_TYPES = ("place_visit", "unconfirmed_visit")


def load_dataframe(source: Path) -> pd.DataFrame:
    """Load the clean dataset from a .parquet or .csv file."""
    if not source.exists():
        raise FileNotFoundError(source)
    if source.suffix == ".parquet":
        return pd.read_parquet(source)
    return pd.read_csv(source)


def format_minutes(total: float | None) -> str:
    """Format a minute count as '12 h 30 min' / '2 h' / '45 min'."""
    if not total:
        return "0 min"
    minutes = int(round(total))
    hours, rest = divmod(minutes, 60)
    if hours and rest:
        return f"{hours} h {rest} min"
    if hours:
        return f"{hours} h"
    return f"{rest} min"


def _activity_modes(df: pd.DataFrame) -> list[tuple[str, float, float]]:
    """Return ``(mode, km, minutes)`` totals for activity segments, largest first."""
    if "title" not in df or df.empty:
        return []
    activities = df.loc[df["type"] == "activity", ["title"]].copy()
    if activities.empty:
        return []
    activities["distance_km"] = (
        df.loc[activities.index, "distance_km"].fillna(0.0) if "distance_km" in df else 0.0
    )
    activities["duration_min"] = (
        df.loc[activities.index, "duration_min"].fillna(0.0) if "duration_min" in df else 0.0
    )
    activities["title"] = activities["title"].fillna("Unknown").astype(str)
    grouped = activities.groupby("title", sort=False)[["distance_km", "duration_min"]].sum()
    modes = [
        (str(title), float(row["distance_km"]), float(row["duration_min"]))
        for title, row in grouped.iterrows()
        if row["distance_km"] > 0 or row["duration_min"] > 0
    ]
    return sorted(modes, key=lambda item: (-item[1], -item[2], item[0]))


@dataclass
class Summary:  # pylint: disable=too-many-instance-attributes
    """Aggregated metrics computed from the clean dataset."""

    days: int = 0
    date_from: str | None = None
    date_to: str | None = None
    total_segments: int = 0
    by_type: dict[str, int] = field(default_factory=dict)
    total_distance_km: float = 0.0
    total_travel_min: float = 0.0
    place_visits: int = 0
    needs_action: int = 0
    top_places: list[tuple[str, int]] = field(default_factory=list)
    by_mode: list[tuple[str, float, float]] = field(default_factory=list)
    busiest_day: tuple[str, float] | None = None
    geocoded: tuple[int, int] | None = None


def summarize(df: pd.DataFrame, top: int = 10) -> Summary:
    """Compute aggregated metrics from the clean dataset DataFrame."""
    if df.empty:
        return Summary()

    days = sorted(str(d) for d in df["day"].dropna().unique())
    by_type = {str(k): int(v) for k, v in df["type"].value_counts().items()}

    distance = df["distance_km"] if "distance_km" in df else pd.Series(dtype=float)
    duration = df["duration_min"] if "duration_min" in df else pd.Series(dtype=float)

    place_mask = df["type"].isin(_PLACE_TYPES)
    confirmed_places = df.loc[df["type"] == "place_visit", "title"].dropna()
    top_places = [
        (str(title), int(count))
        for title, count in confirmed_places.value_counts().head(top).items()
    ]

    needs_action = 0
    if "needs_user_action" in df:
        needs_action = int(df["needs_user_action"].fillna(False).astype(bool).sum())

    busiest_day: tuple[str, float] | None = None
    if "distance_km" in df:
        per_day = df.groupby("day")["distance_km"].sum()
        if not per_day.empty and per_day.max() > 0:
            busiest_day = (str(per_day.idxmax()), float(per_day.max()))

    geocoded: tuple[int, int] | None = None
    if "lat" in df:
        with_address = df["address"].notna().sum() if "address" in df else len(df)
        resolved = int(df["lat"].notna().sum())
        geocoded = (resolved, int(with_address))

    return Summary(
        days=len(days),
        date_from=days[0] if days else None,
        date_to=days[-1] if days else None,
        total_segments=int(len(df)),
        by_type=by_type,
        total_distance_km=float(distance.sum()),
        total_travel_min=float(duration.sum()),
        place_visits=int(place_mask.sum()),
        needs_action=needs_action,
        top_places=top_places,
        by_mode=_activity_modes(df),
        busiest_day=busiest_day,
        geocoded=geocoded,
    )


def render(summary: Summary) -> str:
    """Render a Summary as a human-readable, multi-line console report."""
    if summary.total_segments == 0:
        return "No data to summarize (the dataset is empty)."

    avg_km = summary.total_distance_km / summary.days if summary.days else 0.0
    lines: list[str] = []
    lines.append("Google Maps Timeline - summary")
    lines.append("=" * 34)
    lines.append(
        f"Date range:       {summary.date_from} -> {summary.date_to} ({summary.days} days)"
    )
    lines.append(f"Total entries:    {summary.total_segments}")
    lines.append(f"Place visits:     {summary.place_visits}")
    lines.append(f"Needs action:     {summary.needs_action}")
    lines.append("")
    lines.append(f"Total distance:   {summary.total_distance_km:.1f} km ({avg_km:.1f} km/day)")
    lines.append(f"Total travel:     {format_minutes(summary.total_travel_min)}")
    if summary.by_mode:
        lines.append("")
        lines.append("Travel by mode:")
        for mode, km, minutes in summary.by_mode:
            lines.append(f"  {mode:<18} {km:>6.1f} km   {format_minutes(minutes)}")
    if summary.busiest_day:
        day, km = summary.busiest_day
        lines.append(f"Busiest day:      {day} ({km:.1f} km)")
    if summary.geocoded:
        resolved, total = summary.geocoded
        lines.append(f"Geocoded:         {resolved}/{total} addresses resolved")

    lines.append("")
    lines.append("Entries by type:")
    for seg_type, count in sorted(summary.by_type.items(), key=lambda kv: -kv[1]):
        lines.append(f"  {seg_type:<20} {count}")

    if summary.top_places:
        lines.append("")
        lines.append("Most visited places:")
        for place, count in summary.top_places:
            lines.append(f"  {count:>3}x  {place}")

    return "\n".join(lines)
