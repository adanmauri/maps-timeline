# CLI reference

All commands are invoked as:

```bash
uv run maps-timeline <command> [options]
```

Global flag: `--help` on any command.

---

## `run`

Scrape the Timeline, normalize to CSV/Parquet, and print a summary. Convenience
wrapper around `scrape` + `normalize` + `stats`.

```bash
uv run maps-timeline run --days 7
```

| Option | Default | Description |
| --- | --- | --- |
| `--days` | `3` | Number of days to step back from the displayed day |
| `--raw-out` | *(auto)* | Folder for raw JSONL. Default: new `data/runs/<timestamp>/raw/` |
| `--clean-out` | *(auto)* | Folder for CSV + Parquet. Default: matching run's `clean/` |
| `--serial` | — | Device serial when multiple devices are connected |
| `--prefer` | `u2` | Driver: `u2` (uiautomator2) or `adb` (raw ADB) |
| `--on-error` | `skip` | On navigation error: `skip` the day or `abort` the run |
| `--geocode` | `false` | Resolve addresses to lat/lon via Nominatim |
| `--nominatim-email` | `anon@example.com` | Contact email in Nominatim User-Agent (used when `--geocode`) |
| `--top` | `10` | How many top places to show in the summary |

**Phone required.** Open Google Maps → Rutas → Día before running.

---

## `scrape`

Walk the Timeline day by day backwards and append one JSON line per day.

```bash
uv run maps-timeline scrape --days 30
```

| Option | Default | Description |
| --- | --- | --- |
| `--days` | `3` | Days to scrape backwards |
| `--out` | *(auto)* | Output folder for JSONL. Default: `data/runs/<timestamp>/raw/` |
| `--serial` | — | Device serial |
| `--prefer` | `u2` | `u2` or `adb` |
| `--on-error` | `skip` | `skip` or `abort` |

**Output:** `<out>/timeline.jsonl` plus `<out>/debug/` on failures.

When `--out` is omitted, a versioned run is created and `data/latest` is
updated.

---

## `normalize`

Convert raw JSONL into `timeline.csv` and `timeline.parquet`. **No phone
required.**

```bash
uv run maps-timeline normalize
uv run maps-timeline normalize --geocode --nominatim-email you@example.com
```

| Option | Default | Description |
| --- | --- | --- |
| `--jsonl` | latest run | Path to input `timeline.jsonl` |
| `--out` | inferred | Clean output folder (sibling `clean/` of the JSONL run) |
| `--geocode` | `false` | Add `lat`/`lon` via Nominatim |
| `--nominatim-email` | `anon@example.com` | Contact for Nominatim User-Agent |

**Defaults:** reads `data/latest` → `<run>/raw/timeline.jsonl`, writes to
`<run>/clean/`.

---

## `stats`

Print a console summary of the clean dataset. **No phone required.**

```bash
uv run maps-timeline stats
uv run maps-timeline stats --top 20
```

| Option | Default | Description |
| --- | --- | --- |
| `--source` | latest run | Path to `.parquet` or `.csv` |
| `--top` | `10` | Number of most-visited places to list |

The summary includes date range, total distance and travel time, activity modes,
busiest day, top places, and count of segments needing user action.

---

## `parse-file`

Parse a saved accessibility XML dump offline. **No phone required.**

```bash
uv run maps-timeline parse-file dump_dia.xml
uv run maps-timeline parse-file dump.xml --day 2026-06-06
```

| Argument / option | Required | Description |
| --- | --- | --- |
| `path` | yes | Path to XML dump |
| `--day` | no | Override date (`YYYY-MM-DD`). Default: parse from header |

Prints the full `DayTimeline` JSON and a one-line segment/summary check.

---

## `dump`

Capture a single accessibility dump of the current screen. **Phone required.**

```bash
uv run maps-timeline dump --out dump.xml
```

| Option | Default | Description |
| --- | --- | --- |
| `--out` | `dump.xml` | Output file path |
| `--serial` | — | Device serial |
| `--prefer` | `u2` | `u2` or `adb` |

Useful for calibrating selectors and building offline test fixtures.

---

## Makefile shortcuts

The [Makefile](../Makefile) wraps common invocations:

```bash
make install-dev              # uv sync + pre-commit hooks
make scrape ARGS="--days 7"
make normalize ARGS="--geocode --nominatim-email you@example.com"
make parse-file FILE=dump_dia.xml
make dump OUT=dump.xml
make quality && make test     # lint + type-check + security; then pytest
```

See [`DEVELOPMENT.md`](DEVELOPMENT.md) for all `make` targets.

---

## Exit codes

| Code | Meaning |
| --- | --- |
| `0` | Success |
| `1` | Missing input files, dataset not found, or typer validation error |

Scrape may complete with partial success (`days_failed` listed in output) when
`--on-error skip` and individual days fail navigation.
