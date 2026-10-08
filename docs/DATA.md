# Data formats

This document describes the on-disk artifacts produced by `maps-timeline`.
All paths under `data/` are **gitignored** and contain sensitive location history.

## Run layout

```
data/
├── latest                    # single line: absolute path to latest run dir
├── cache/
│   ├── geocode.json          # Nominatim cache (only with --geocode)
│   └── places.json           # place ID -> {title, address} learned from scrapes
├── drafts/                   # local PR/issue drafts from agent skills (gitignored)
│   ├── PR.md
│   └── ISSUE.md
└── runs/
    └── YYYY-MM-DD_HHMMSS/
        ├── raw/
        │   ├── timeline.jsonl
        │   ├── export.json       # official Timeline export (import / --export)
        │   └── debug/
        └── clean/
            ├── timeline.csv
            └── timeline.parquet
```

`data/latest` is rewritten on every default scrape so `normalize` and `stats`
can find the most recent export without explicit paths.

---

## Raw JSONL (`timeline.jsonl`)

One **JSON object per line**, one line per scraped day. Produced by `scrape` /
`run`; consumed by `normalize`.

### Top-level fields (`DayTimeline`)

| Field | Type | Description |
| --- | --- | --- |
| `day` | `YYYY-MM-DD` | Calendar date for this Timeline day |
| `header_text` | string \| null | Date header exactly as shown ("Sat Jun 6, 2026") |
| `summary` | object | On-screen day totals (see below) |
| `segments` | array | Ordered list of Timeline entries |
| `scraped_at` | ISO datetime | When this day was captured |

### `summary` object (`DaySummary`)

| Field | Type | Example |
| --- | --- | --- |
| `total_distance_text` | string \| null | `"18 km"` |
| `total_duration_text` | string \| null | `"1 h 15 min"` |
| `visit_count` | int \| null | `5` |

### `segments[]` object (`Segment`)

| Field | Type | Description |
| --- | --- | --- |
| `type` | string | See [segment types](#segment-types) |
| `title` | string \| null | Place name or transport mode |
| `address` | string \| null | Street address when present |
| `time_anchor` | string \| null | `range`, `departure`, `arrival`, `all_day` |
| `start_time` | string \| null | Raw clock text, e.g. `"4:49 PM"` |
| `end_time` | string \| null | Raw clock text |
| `duration_text` | string \| null | e.g. `"10 min"`, `"1 h 15 min"` |
| `distance_text` | string \| null | e.g. `"2,4 km"`, `"850 m"` |
| `confirmed` | bool \| null | `false` for unconfirmed visits |
| `needs_user_action` | bool | `true` when Google could not resolve the segment |
| `raw_desc` | string | Full `content-desc` for traceability |

### Example line (abbreviated)

```json
{
  "day": "2026-06-06",
  "header_text": "Fri Jun 6, 2026",
  "summary": {"visit_count": 3, "total_distance_text": "12 km"},
  "segments": [
    {
      "type": "place_visit",
      "title": "Home",
      "address": "C. Example 123",
      "start_time": "8:00 AM",
      "end_time": "9:15 AM",
      "needs_user_action": false,
      "raw_desc": "Home, C. Example 123, 8:00 AM - 9:15 AM"
    },
    {
      "type": "activity",
      "title": "En automóvil",
      "distance_text": "2,4 km",
      "duration_text": "10 min",
      "raw_desc": "En automóvil · 2,4 km · 10 min"
    }
  ],
  "scraped_at": "2026-06-16T14:30:22.123456"
}
```

### Segment types

| `type` | UI meaning | `needs_user_action` |
| --- | --- | --- |
| `place_visit` | Confirmed place visit | `false` |
| `activity` | Trip leg (car, walk, transit, …) | `false` |
| `unconfirmed_visit` | `"¿Visitaste …?"` prompt | `true` |
| `unknown_visit` | `"Visita desconocida"` | `true` |
| `missing_transit` | `"Modo de viaje faltante"` | `true` |

Visit counting for summary cross-check includes `place_visit`, `unconfirmed_visit`,
and `unknown_visit` (see `DayTimeline.place_visits`).

---

## Official Timeline export (`export.json`)

The file Android writes from *Settings → Location → Location services → Timeline →
Export Timeline data* (often localized, e.g. `Rutas.json`). `import` and `run --export`
copy it **verbatim** into `raw/export.json`; it is the second raw input of stage 2.

| Top-level key | Read? | Contents |
| --- | :---: | --- |
| `semanticSegments[].visit` | Yes | `topCandidate.placeId`, `semanticType`, `placeLocation.latLng`, `probability`, `hierarchyLevel` |
| `semanticSegments[].activity` | Yes | `topCandidate.type` (e.g. `WALKING`), `distanceMeters`, `start`/`end` `latLng` |
| `semanticSegments[].timelinePath` | No | GPS points along the day |
| `semanticSegments[].timelineMemory` | No | Trip summaries |
| `rawSignals` | No | Raw GPS fixes, activity recognition, **Wi-Fi scans** |
| `userLocationProfile` | No | Frequent places (home/work), travel-mode affinities |

Timestamps are ISO 8601 with UTC offset (`2026-06-06T16:59:00.000-03:00`); coordinates
are strings like `"-34.6037°, -58.3816°"`. The export has **no place names or
addresses** — that is what the scrape adds. Takeout files (`timelineObjects`) are not
supported.

---

## Clean dataset (`timeline.csv` / `timeline.parquet`)

Produced by `normalize`. **One row per segment** (not per day).

| Column | Type | Source |
| --- | --- | --- |
| `day` | string | `YYYY-MM-DD` |
| `type` | string | Segment type |
| `title` | string \| null | Place name or mode |
| `address` | string \| null | Address text |
| `start_iso` | string \| null | ISO 8601 from `day` + `start_time` |
| `end_iso` | string \| null | ISO 8601 from `day` + `end_time` |
| `duration_min` | float \| null | Parsed from `duration_text` |
| `distance_km` | float \| null | Parsed from `distance_text` (meters → km) |
| `confirmed` | bool \| null | As scraped |
| `needs_user_action` | bool | As scraped |
| `lat` | float \| null | Only with `--geocode` |
| `lon` | float \| null | Only with `--geocode` |

### Parsing rules (normalization)

| Raw text | Parsed value |
| --- | --- |
| `"1 h 15 min"` | `duration_min = 75` |
| `"42 min"` | `duration_min = 42` |
| `"2,4 km"` | `distance_km = 2.4` (European decimal comma) |
| `"850 m"` | `distance_km = 0.85` |
| `"4:59 PM"` on day `2026-06-06` | `start_iso = 2026-06-06T16:59:00` |

Times use 12-hour format with AM/PM as shown in the Maps UI.

### Merged dataset

When the run has an official export, the dataset has **one row per official visit or
trip**, plus one row per scraped entry that matched none. The scraped side is the whole
scrape history (see below), not only the run's own JSONL. Columns above keep their
meaning, with these differences and additions:

| Column | Type | Source |
| --- | --- | --- |
| `start_iso` / `end_iso` | string | Local wall-clock time from the export (seconds precision) |
| `duration_min` | float | Elapsed time from the export — **visits included** (stay length) |
| `distance_km` | float \| null | `distanceMeters` from the export, else the UI text |
| `lat` / `lon` | float \| null | Visit place location (`--geocode` only fills rows without it) |
| `start_lat` / `start_lon` / `end_lat` / `end_lon` | float \| null | Trip endpoints |
| `place_id` | string \| null | Google place ID of the visit |
| `semantic_type` | string \| null | `UNKNOWN`, `INFERRED_HOME`, `INFERRED_WORK`, `SEARCHED_ADDRESS`, … |
| `probability` | float \| null | Google's confidence in the visit / activity |
| `hierarchy_level` | int \| null | `0` top-level visit, `1` visit nested inside another |
| `activity_type` | string \| null | `WALKING`, `IN_PASSENGER_VEHICLE`, `IN_BUS`, `FLYING`, … |
| `tz_offset_min` | int \| null | UTC offset of the start time, in minutes |
| `source` | string | `both` (matched), `export` (official only), `scrape` (UI only) |
| `title_source` | string \| null | `scrape`, `place_id` (learned from another visit to the same place, in this or an earlier run), `activity_type` (label learned from another trip of that type), `export` (raw activity type) |
| `match_score` | float \| null | Time overlap (intersection over union) with the matched scraped entry |

**How entries are matched:** per scraped day, each entry is paired with the official
segment of the same kind (visit ↔ `place_visit` / `unconfirmed_visit` / `unknown_visit`;
trip ↔ `activity` / `missing_transit`) whose local interval overlaps it best, with an
intersection over union of at least 0.5. Arrival / departure anchors cover the rest of the
day, so a visit across midnight can absorb one entry from each day. Entries without clock
times stay `scrape` rows.

**Place-name cache:** every merge writes the names it learned to
`data/cache/places.json` (`{"<place ID>": {"title": …, "address": …}}`) and reuses
them, so places named in an earlier run stay named, and `run --export` only plans days
for places that are still unnamed. Delete the file to start over. It contains real place
names and addresses: treat it like the rest of `data/`.

**Scrape history:** with an export, `normalize`, `import` and `run` read the
`raw/timeline.jsonl` of every run under `data/runs/` (oldest first; the run being built
goes last), keeping the latest capture of each day. The planner uses the same history:
names learned from it count as known (even for runs that never reached the merge), and
days captured **completely** are not planned again. A capture is complete when the run
started after the day ended; a day captured on its own date may miss its last hours and
is captured again while the export does not cover it. Days outside a versioned run (e.g.
`--jsonl` elsewhere) count as complete. Deleting a run removes its days from the history;
the names it taught stay in the cache.

**Caveats:** visits nested inside another (`hierarchy_level = 1`) may have no
counterpart in the app and stay `export` rows, so place counts can be slightly higher; the
planner stops looking for such a place after two captured days. Matching assumes the app
shows each segment in its own local time; trips abroad are worth spot-checking.

### Filtering for analysis

```python
import pandas as pd

df = pd.read_parquet("data/runs/.../clean/timeline.parquet")

# High-confidence rows only
clean = df[~df["needs_user_action"]]

# Visits vs trips
visits = df[df["type"] == "place_visit"]
trips = df[df["type"] == "activity"]
```

---

## Geocoding

When `--geocode` is passed to `normalize` or `run`:

1. Collect unique non-empty `address` values from rows that have no coordinates yet
   (with an official export, only scrape-only rows).
2. Query [Nominatim](https://nominatim.org/) (OpenStreetMap) at 1 req/s.
3. Cache results in `data/cache/geocode.json` (keyed by address string).
4. Add `lat` and `lon` columns to each row.

**Limitations:**

- Returns the **geocoded address / POI location**, not GPS breadcrumbs along a
  route.
- Approximate for vague addresses (no street number).
- Requires network; failures leave `lat`/`lon` empty without aborting
  normalization.
- Pass `--nominatim-email` so requests include a contact per Nominatim policy.

---

## Debug artifacts (`raw/debug/`)

Written during scraping when validation fails. Files are named
`{YYYY-MM-DD}_{tag}.xml` and `.png` (`.txt` for `error`):

| Tag | Trigger |
| --- | --- |
| `wrong_screen` | Timeline day list not detected |
| `collapsed_panel` | Bottom sheet still collapsed |
| `empty` | Parser found 0 segments but summary shows visits |
| `no_prev_button` | "Día anterior" button not found (screenshot only) |
| `error` | Device, adb or app error stopped the walk (traceback only; the date is the day being left or read) |

Use these with `parse-file` to reproduce parser issues offline.

---

## Reprocessing

Because stage 1 stores **raw text**, you can improve parsers and re-run:

```bash
uv run maps-timeline normalize --jsonl data/runs/2026-06-16_143022/raw/timeline.jsonl
```

No changes to the JSONL format are needed unless `models.py` fields are renamed
or removed (document breaking changes in release notes).
