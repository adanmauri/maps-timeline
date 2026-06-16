"""Stage 2: turn the raw JSONL into a clean dataset (CSV + Parquet).

Splitting scraping from normalization makes it possible to reprocess the raw data
without re-scanning the phone (e.g. after improving the duration parser).
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

import pandas as pd

if TYPE_CHECKING:
    from .geocode import NominatimGeocoder

_TIME_FMT = "%I:%M %p"  # "4:59 PM"


def _clean(text: str | None) -> str | None:
    """Normalize whitespace in raw UI text."""
    if text is None:
        return None
    return text.replace("\xa0", " ").strip()


def parse_duration_minutes(text: str | None) -> float | None:
    """'1 h 15 min' -> 75 ; '42 min' -> 42 ; '2 h' -> 120."""
    text = _clean(text)
    if not text:
        return None
    hours = re.search(r"(\d+)\s*h", text)
    minutes = re.search(r"(\d+)\s*min", text)
    total = 0.0
    if hours:
        total += int(hours.group(1)) * 60
    if minutes:
        total += int(minutes.group(1))
    return total or None


def parse_distance_km(text: str | None) -> float | None:
    """'2,4 km' -> 2.4 ; '14 km' -> 14.0 ; '850 m' -> 0.85."""
    text = _clean(text)
    if not text:
        return None
    m = re.match(r"([\d.,]+)\s*(km|m)\b", text)
    if not m:
        return None
    value = (
        float(m.group(1).replace(".", "").replace(",", "."))
        if "," in m.group(1)
        else float(m.group(1))
    )
    return value / 1000 if m.group(2) == "m" else value


def to_iso(day: str, time_text: str | None) -> str | None:
    """Combine the day date (YYYY-MM-DD) with a time '4:59 PM' -> ISO."""
    time_text = _clean(time_text)
    if not time_text:
        return None
    try:
        t = datetime.strptime(time_text, _TIME_FMT).time()
        d = datetime.strptime(day, "%Y-%m-%d").date()
        return datetime.combine(d, t).isoformat()
    except ValueError:
        return None


def normalize(jsonl_path: Path, out_dir: Path, geocoder: NominatimGeocoder | None = None) -> Path:
    """Flatten the JSONL into a DataFrame and write it as CSV and Parquet.

    If a `geocoder` is passed, add lat/lon columns by resolving the addresses
    (cached, one query per unique address).
    """
    rows = []
    with jsonl_path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            day_obj = json.loads(line)
            day = str(day_obj["day"])
            for seg in day_obj.get("segments", []):
                rows.append(
                    {
                        "day": day,
                        "type": seg.get("type"),
                        "title": seg.get("title"),
                        "address": seg.get("address"),
                        "start_iso": to_iso(day, seg.get("start_time")),
                        "end_iso": to_iso(day, seg.get("end_time")),
                        "duration_min": parse_duration_minutes(seg.get("duration_text")),
                        "distance_km": parse_distance_km(seg.get("distance_text")),
                        "confirmed": seg.get("confirmed"),
                        "needs_user_action": seg.get("needs_user_action"),
                    }
                )

    if geocoder is not None:
        unique_addresses = {r["address"] for r in rows if r.get("address")}
        print(f"[·] Geocoding {len(unique_addresses)} unique addresses (Nominatim)...")
        coords = {addr: geocoder.geocode(addr) for addr in unique_addresses}
        for r in rows:
            r["lat"], r["lon"] = coords.get(r.get("address"), (None, None))

    df = pd.DataFrame(rows)
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / "timeline.csv"
    parquet_path = out_dir / "timeline.parquet"
    df.to_csv(csv_path, index=False)
    df.to_parquet(parquet_path, index=False)
    print(f"[✓] {len(df)} segments normalized -> {csv_path.name}, {parquet_path.name}")
    return csv_path
