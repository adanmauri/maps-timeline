# Data formats

This document describes the on-disk artifacts produced by `maps-timeline`.
All paths under `data/` are **gitignored** and contain sensitive location history.

## Run layout

```
data/
├── latest                    # single line: absolute path to latest run dir
├── cache/
│   └── geocode.json          # Nominatim cache (only with --geocode)
├── drafts/                   # local PR/issue drafts from agent skills (gitignored)
│   ├── PR.md
│   └── ISSUE.md
└── runs/
    └── YYYY-MM-DD_HHMMSS/
        ├── raw/
        │   ├── timeline.jsonl
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

1. Collect unique non-empty `address` values from all rows.
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
`{YYYY-MM-DD}_{tag}.xml` and `.png`:

| Tag | Trigger |
| --- | --- |
| `wrong_screen` | Timeline day list not detected |
| `collapsed_panel` | Bottom sheet still collapsed |
| `empty` | Parser found 0 segments but summary shows visits |
| `no_prev_button` | "Día anterior" button not found (screenshot only) |

Use these with `parse-file` to reproduce parser issues offline.

---

## Reprocessing

Because stage 1 stores **raw text**, you can improve parsers and re-run:

```bash
uv run maps-timeline normalize --jsonl data/runs/2026-06-16_143022/raw/timeline.jsonl
```

No changes to the JSONL format are needed unless `models.py` fields are renamed
or removed (document breaking changes in release notes).
