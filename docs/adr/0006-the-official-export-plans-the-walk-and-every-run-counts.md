# 0006. The official export plans the walk, and every run counts

**Status:** Accepted · **Date:** 2026-10-08

## Context

The scraper can only step back one day at a time
([ADR-0001](0001-the-scraper-reads-the-timeline-from-the-accessibility-tree.md)), and capturing a
day fully (panel expansion, scrolling, stable-screen waits) costs much more than tapping past it.
Once the export is merged
([ADR-0005](0005-the-official-export-is-merged-by-time-overlap-and-place-id.md)), one name per
place ID is enough: a place only needs one of its days captured. The export already
lists, for every day, which place IDs were visited. A walk over years of history can also be
interrupted (Ctrl+C, a lost USB connection) and has to be resumable.

## Options

- **Walk N days and capture them all (`--days`):** simple and still available, but it captures
  every day and must walk back as far as the oldest place.
- **Capture only planned days, plan from the export:** choose the fewest days that show every
  unnamed place, and only step over the others (header check and tap).
- **Jump to planned days with the calendar:** fewest screens, but depends on another part of the
  app's UI; not explored yet.

## Decision

- `planner.py` is pure. From the official export, the names already known and the days already
  captured, it returns a `ScrapePlan`:
  1. Unnamed visits up to the start day (`--until`, today by default), grouped by day.
  2. Days captured completely by an earlier run are never planned again; each counts as an attempt
     for the unnamed places it shows. A place still unnamed after `MAX_ATTEMPTS` (2) captured days,
     or with no uncaptured day left, is reported as skipped.
  3. The target places are every place left, or with `--since` those with an uncaptured visit on
     or after that day. Each needs only its most recent such day, which bounds how far back the
     walk goes.
  4. The days the export does not reach (from its last day to the start day, minus complete
     captures and days before `--since`) are always planned. A greedy set cover, seeded with them
     and preferring recent days on ties, picks the fewest extra days that show every target.
- `history.py` reads every run's `raw/timeline.jsonl` as one scrape history: the latest capture of
  a day wins, and a capture is complete when its run started after the day ended. The planner and
  the merge both use it, together with the place-name cache, so an interrupted walk resumes instead
  of starting over.
- `pipeline.scrape(only_days=...)` captures the planned days and steps over the rest, reusing the
  dump left by the previous tap to verify the header date
  ([ADR-0004](0004-the-day-comes-from-date-arithmetic-the-header-only-verifies-it.md)). It stops
  past the oldest planned day, prints progress with a time estimate every `PROGRESS_EVERY` (25)
  days. Ctrl+C or a device error ends the walk, not the process: every captured day is kept for
  the merge, and a device error's traceback goes to `raw/debug/`.
- `--days` keeps the original behavior: capture every day walked.

## Consequences

### Positive

- The walk captures far fewer days than it visits, and stops as soon as every target place has a
  day.
- Running the same command again continues where the last run stopped; no day captured completely
  is captured again.
- Places the app does not show stop being looked for after two attempts.

### Negative / trade-offs

- The walk still visits every day between the start and the oldest planned day; only the capture
  is skipped. Opening the Timeline on the newest planned day saves the newer ones, which the plan
  suggests when it is a week or more back.
- The plan relies on the merge's matching: a place whose visits never match is skipped, not named.
- Deleting a run removes its days from the history (the names it taught stay in the cache).

### Follow-ups

- `.agents/rules/scraper-guardrails.md` cites this ADR for planned walks.
- `docs/ARCHITECTURE.md` (*Planned walk*) and `docs/CLI.md` describe the options and output.
