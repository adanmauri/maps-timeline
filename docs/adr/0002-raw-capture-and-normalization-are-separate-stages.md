# 0002. Raw capture and normalization are separate stages

**Status:** Accepted · **Date:** 2026-10-08

## Context

Walking the Timeline needs the phone and takes time per day
([ADR-0001](0001-the-scraper-reads-the-timeline-from-the-accessibility-tree.md)). Turning what the
app shows into numbers is a separate concern that keeps changing: durations ("1 h 15 min"),
distances with a decimal comma ("2,4 km"), 12-hour clock times, entries anchored to a departure or
an arrival only, and, later, the merge with the official export. If the walk produced the final
dataset directly, every improvement to that interpretation would mean walking the phone again.

## Options

- **One stage, straight to the final dataset:** one file and one command, but any parsing change
  needs a new walk.
- **Keep each day's raw XML dump:** nothing is lost, but the files are large, hold every node on
  the screen, and every reprocess parses XML again.
- **Two stages, raw text first:** the walk saves each day's entries with their text as shown; a
  second stage turns that text into typed columns and can run any number of times without the
  phone. The raw format becomes a contract to keep.

## Decision

- **Stage 1, scrape:** one JSON object per day (`DayTimeline`) appended to `raw/timeline.jsonl` as
  soon as the day is parsed. Entries are split into fields and classified by type, but times,
  durations and distances stay as the app shows them (`start_time: "4:49 PM"`,
  `distance_text: "2,4 km"`), with the full `content-desc` kept in `raw_desc`.
- **Stage 2, normalize:** `normalize` (and `import`, with an official export) reads the raw JSONL
  and writes `clean/timeline.csv` and `clean/timeline.parquet`: ISO times, minutes, kilometers.
  It never touches the device and can be re-run after a parser change.
- **Versioned runs:** each scrape writes to its own `data/runs/<YYYY-MM-DD_HHMMSS>/` folder, with
  `raw/` and `clean/`, and `data/latest` records the most recent run so `normalize` and `stats`
  work without paths. The official export, when used, is copied verbatim to `raw/export.json`, the
  second raw input of stage 2.
- Changes to `models.py` keep the raw JSONL readable, or document the incompatibility.

## Consequences

### Positive

- A parser or merge improvement is applied to every past run with `normalize`, without the phone.
- A walk that stops halfway keeps every day already written.
- Runs never overwrite each other.

### Negative / trade-offs

- Two commands (or `run`, which chains them), and two formats to document (`docs/DATA.md`).
- The raw JSONL schema is a compatibility promise: renaming or removing a field breaks reprocessing
  of older runs.
- Stage 1 already classifies entries, so a classification change still needs either a new walk or
  re-parsing from `raw_desc`.

### Follow-ups

- [ADR-0006](0006-the-official-export-plans-the-walk-and-every-run-counts.md) reads every run's raw
  JSONL as one history.
- `docs/DATA.md` documents both formats; `docs/ARCHITECTURE.md` the data flow.
