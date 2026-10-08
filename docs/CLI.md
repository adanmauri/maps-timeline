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
uv run maps-timeline run --export Timeline.json                 # planned from the export
uv run maps-timeline run --export Timeline.json --since 2025-11-01  # shorter walk
uv run maps-timeline run --export Timeline.json --since 2026-01-01 --until 2026-03-31
```

**Planned mode** (`--export` without `--days`): the export lists the visits whose place
has no name yet. Known names come from `data/cache/places.json` and from the scrape of
every run under `data/runs/`. The plan walks back only as far as needed and fully
captures only the fewest days that show those places, plus the days the export does not
reach (from its last day to today); other days are stepped over. Days earlier runs
already captured completely are never planned again, and a place still unnamed after two
captured days is skipped. Before touching the phone it prints `Plan: capture X of Y days
(back to YYYY-MM-DD) …`, a tip when the newest planned day is a week or more back (open the
Timeline on that day to skip the newer ones), and how many places are skipped. It exits
without scraping when there is nothing left to capture.

During the walk a progress line (`walked X/Y days, captured A/B, about N min left`) is
printed every 25 days. **Ctrl+C or a device error stops the walk without losing it:** the
days captured so far are merged, and running the same command again continues where the
plan left off.

| Option              | Default            | Description                                                                                                                                                                                                                                         |
|---------------------|--------------------|-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `--days`            | `3`, or planned    | Number of days to step back from the displayed day. With `--export`, omit it to plan the walk                                                                                                                                                       |
| `--raw-out`         | *(auto)*           | Folder for raw JSONL. Default: new `data/runs/<timestamp>/raw/`                                                                                                                                                                                     |
| `--clean-out`       | *(auto)*           | Folder for CSV + Parquet. Default: matching run's `clean/`                                                                                                                                                                                          |
| `--serial`          | —                  | Device serial when multiple devices are connected                                                                                                                                                                                                   |
| `--prefer`          | `u2`               | Driver: `u2` (uiautomator2) or `adb` (raw ADB)                                                                                                                                                                                                      |
| `--on-error`        | `skip`             | On navigation error: `skip` the day or `abort` the run                                                                                                                                                                                              |
| `--geocode`         | `false`            | Resolve addresses to lat/lon via Nominatim                                                                                                                                                                                                          |
| `--nominatim-email` | `anon@example.com` | Contact email in Nominatim User-Agent (used when `--geocode`)                                                                                                                                                                                       |
| `--top`             | `10`               | How many top places to show in the summary                                                                                                                                                                                                          |
| `--export`          | —                  | Official Timeline export to copy into the run (`raw/export.json`) and merge. Validated before scraping starts; without `--days` it plans the walk                                                                                                   |
| `--since`           | no limit           | Planned mode: only look for places visited on or after this day (`YYYY-MM-DD`); their older visits get the name too. Days the export does not reach are also limited to it. The plan line shows how many unnamed visits that names                  |
| `--until`           | today              | Planned mode: only plan days on or before this day (`YYYY-MM-DD`). The walk still starts from the day shown in Maps, so newer days are stepped over (or open the Timeline on `--until` first, as the plan's tip says). Must not be before `--since` |

**Phone required.** Open Google Maps → Rutas → Día before running. The device is
connected before the run folder is created, so a missing phone leaves no empty run.

---

## `scrape`

Walk the Timeline day by day backwards and append one JSON line per day.

```bash
uv run maps-timeline scrape --days 30
uv run maps-timeline scrape --export Timeline.json   # planned walk; merge later with normalize
```

| Option       | Default         | Description                                                                                                                               |
|--------------|-----------------|-------------------------------------------------------------------------------------------------------------------------------------------|
| `--days`     | `3`, or planned | Days to scrape backwards. With `--export`, omit it to plan the walk                                                                       |
| `--out`      | *(auto)*        | Output folder for JSONL. Default: `data/runs/<timestamp>/raw/`                                                                            |
| `--serial`   | —               | Device serial                                                                                                                             |
| `--prefer`   | `u2`            | `u2` or `adb`                                                                                                                             |
| `--on-error` | `skip`          | `skip` or `abort`                                                                                                                         |
| `--export`   | —               | Official Timeline export to copy into `<out>/export.json` for `normalize` to merge; without `--days` it plans the walk exactly like `run` |
| `--since`    | no limit        | Planned mode: only look for places visited on or after this day (`YYYY-MM-DD`)                                                            |
| `--until`    | today           | Planned mode: only plan days on or before this day (`YYYY-MM-DD`)                                                                         |

**Output:** `<out>/timeline.jsonl` plus `<out>/debug/` on failures (including
`{date}_error.txt` with the traceback when a device error stops the walk).

When `--out` is omitted, a versioned run is created and `data/latest` is
updated.

---

## `normalize`

Convert raw JSONL and/or the official Timeline export into `timeline.csv` and
`timeline.parquet`. When both are available they are merged (see
[`DATA.md`](DATA.md#merged-dataset)). **No phone required.**

```bash
uv run maps-timeline normalize
uv run maps-timeline normalize --geocode --nominatim-email you@example.com
uv run maps-timeline normalize --jsonl run/raw/timeline.jsonl --export Timeline.json
```

| Option              | Default                      | Description                                                |
|---------------------|------------------------------|------------------------------------------------------------|
| `--jsonl`           | latest run                   | Path to input `timeline.jsonl`                             |
| `--export`          | `raw/export.json` if present | Official Timeline export to merge                          |
| `--out`             | inferred                     | Clean output folder (sibling `clean/` of the run's `raw/`) |
| `--geocode`         | `false`                      | Add `lat`/`lon` via Nominatim to rows that have none       |
| `--nominatim-email` | `anon@example.com`           | Contact for Nominatim User-Agent                           |

**Defaults:** reads `data/latest` → `<run>/raw/timeline.jsonl` and
`<run>/raw/export.json` (whichever exist), writes to `<run>/clean/`. Passing only
`--export` normalizes the export on its own. With an export, the scrapes of every other
run under `data/runs/` are merged too (the latest capture of each day wins), so the
dataset holds every day ever scraped. Without an export only the given JSONL is used.

---

## `import`

Copy the official on-device Timeline export into a run and build the clean dataset.
**No phone required.**

```bash
uv run maps-timeline import Timeline.json                          # new run
uv run maps-timeline import Timeline.json --run "$(cat data/latest)"  # merge with a scrape
```

| Argument / option | Default      | Description                                                                                                     |
|-------------------|--------------|-----------------------------------------------------------------------------------------------------------------|
| `path`            | *(required)* | Export saved from *Settings → Location → Location services → Timeline → Export Timeline data*                   |
| `--run`           | new run      | Existing run folder to attach the export to; its scrape (if any) wins over other runs' captures of the same day |

The file is validated before any run is created or modified, copied verbatim to
`<run>/raw/export.json`, and `data/latest` is pointed at the run. The scrapes of every run
under `data/runs/` are merged with it. Only the Android
on-device format (top-level `semanticSegments`) is supported; Takeout files are rejected.

---

## `stats`

Print a console summary of the clean dataset. **No phone required.**

```bash
uv run maps-timeline stats
uv run maps-timeline stats --top 20
```

| Option     | Default    | Description                           |
|------------|------------|---------------------------------------|
| `--source` | latest run | Path to `.parquet` or `.csv`          |
| `--top`    | `10`       | Number of most-visited places to list |

The summary includes date range, total distance and travel time, activity modes,
busiest day, top places, and count of segments needing user action.

---

## `parse-file`

Parse a saved accessibility XML dump offline. **No phone required.**

```bash
uv run maps-timeline parse-file dump_dia.xml
uv run maps-timeline parse-file dump.xml --day 2026-06-06
```

| Argument / option | Required | Description                                              |
|-------------------|----------|----------------------------------------------------------|
| `path`            | yes      | Path to XML dump                                         |
| `--day`           | no       | Override date (`YYYY-MM-DD`). Default: parse from header |

Prints the full `DayTimeline` JSON and a one-line segment/summary check.

---

## `dump`

Capture a single accessibility dump of the current screen. **Phone required.**

```bash
uv run maps-timeline dump --out dump.xml
```

| Option     | Default    | Description      |
|------------|------------|------------------|
| `--out`    | `dump.xml` | Output file path |
| `--serial` | —          | Device serial    |
| `--prefer` | `u2`       | `u2` or `adb`    |

Useful for calibrating selectors and building offline test fixtures.

---

## Makefile shortcuts

The [Makefile](../Makefile) wraps common invocations:

```bash
make scrape ARGS="--days 7"
make normalize ARGS="--geocode --nominatim-email you@example.com"
make parse-file FILE=dump.xml
make dump OUT=dump.xml
make run ARGS="stats --top 20"
```

`make help` lists every target; the development ones are in [`DEVELOPMENT.md`](DEVELOPMENT.md).

---

## Exit codes

| Code | Meaning                                                                                                                   |
|------|---------------------------------------------------------------------------------------------------------------------------|
| `0`  | Success                                                                                                                   |
| `1`  | Missing input files, dataset not found, unsupported Timeline export, `--since` after `--until`, or typer validation error |

Scrape may complete with partial success (`days_failed` listed in output) when
`--on-error skip` and individual days fail navigation. A walk stopped by Ctrl+C or a
device error also exits with `0` after keeping (and, for `run`, merging) the days
captured so far; the output says `Walk stopped early (...)`.
