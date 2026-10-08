# 0005. The official export is merged by time overlap and place ID

**Status:** Accepted · **Date:** 2026-10-08

## Context

Two sources describe the same history, each with what the other lacks:

- The **scrape** has what the app shows: place names, addresses, transport labels, and whether
  Google still needs the user to confirm a visit. It covers only the days walked, with clock
  times to the minute and no coordinates.
- The **official on-device export** (`semanticSegments` visits and activities) has the whole
  history with timezone-aware times, coordinates, distances and a Google place ID per visit, but
  no names or addresses.

There is no shared key: the app never shows a place ID, and the export never has a name. What both
have is the time each visit or trip happened, and the place ID ties every visit to the same place
together, including on days that were never scraped.

## Options

- **Keep the sources apart:** two datasets the user has to join by hand.
- **Match by start time:** simple, but entries anchored only to a departure or an arrival (the
  first and last of a day) have one time each, and small offsets break exact matches.
- **Match by interval overlap, then propagate by place ID:** each scraped entry is paired with the
  official segment whose time interval overlaps it best, and a name learned on one matched visit
  applies to every visit with the same place ID.

## Decision

- `official.py` parses the export (visits and activities only; `timelinePath`, `timelineMemory`,
  `rawSignals` and `userLocationProfile` are ignored).
- **Intervals.** Scraped entries become local wall-clock intervals: `range` as shown (wrapping past
  midnight), `departure` from midnight to the time, `arrival` from the time to midnight,
  `all_day` the whole day. Official intervals drop the UTC offset and are truncated to minutes,
  like the app's clock.
- **Scores.** Per scraped day, only official segments of the compatible kind (visit or activity)
  that touch that day are scored, by intersection over union, and kept at `MIN_MATCH_SCORE`
  (0.5) or more.
- **Assignment.** Greedy by score: each scraped entry is used once, and each official segment once
  per day, so a visit across midnight takes the arrival entry of one day and the departure entry of
  the next.
- **Propagation.** The most common scraped `(title, address)` per place ID names every other visit
  to that place; the most common label per activity type names unmatched trips. Learned names are
  kept in `data/cache/places.json` and reused by later merges; names learned in the current merge
  win over cached ones.
- **Rows.** One row per official segment, plus one per scraped entry that matched none. `source`
  (`both`, `export`, `scrape`), `title_source` (`scrape`, `place_id`, `activity_type`, `export`)
  and `match_score` record where each value came from. Without an export, `normalize` produces the
  scrape-only dataset unchanged.

## Consequences

### Positive

- Every visit in the export gets coordinates and, once its place has been seen on any scraped day,
  a readable name, even on days never walked.
- Each row says how it was named and how well it matched, so analysts can filter.

### Negative / trade-offs

- A scraped entry without clock times cannot be matched and stays a `scrape` row.
- Visits nested inside another (`hierarchy_level = 1`) may have no counterpart in the app and stay
  `export` rows.
- Matching assumes the app shows each segment in its own local time; trips across time zones are
  worth spot-checking.
- A wrong match would propagate a wrong name to every visit of that place; the cache keeps it
  until it is deleted or a later merge learns another name.

### Follow-ups

- [ADR-0006](0006-the-official-export-plans-the-walk-and-every-run-counts.md) uses the learned names
  to choose which days to scrape.
- `docs/DATA.md` documents the merged columns; `docs/ARCHITECTURE.md` (*Merging with the official
  export*) the steps.
