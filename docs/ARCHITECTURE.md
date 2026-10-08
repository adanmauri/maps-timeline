# Architecture

This document explains how `maps-timeline` reads the Google Maps Timeline from
a phone and turns it into a clean dataset. For usage and CLI options see the
[README](../README.md) and [`CLI.md`](CLI.md); for schemas see [`DATA.md`](DATA.md); for
setup and conventions see [`DEVELOPMENT.md`](DEVELOPMENT.md). Why it is built this way, with
the options that were weighed, is recorded in the [ADRs](adr/README.md).

## The big picture

There is no Google API involved. The tool **reads what the Google Maps app draws
on the screen**, the same information a screen reader (accessibility service)
would announce. Android exposes the full UI of any app as an XML tree (the
"accessibility hierarchy"); `maps-timeline` asks the phone for that XML,
extracts Timeline entries, taps "Día anterior" (*Previous day*), and repeats.

The work is split into **two independent stages**:

1. **Scrape** — save raw text exactly as the app shows it (`timeline.jsonl`).
2. **Normalize** — parse durations, distances, and clock times into a flat
   dataset (`timeline.csv` + `timeline.parquet`).

Decoupling means you can **reprocess** raw exports after improving the parser
without re-scanning the phone.

Stage 2 has an optional second input: the **official on-device Timeline export**
(`raw/export.json`, saved from Android settings). It has coordinates and place IDs but
no names; the scrape has names but no coordinates. When both are present, `merge.py`
aligns them by time and produces one dataset with the best of each.

## Data flow

```text
Phone (Google Maps, Timeline / Rutas, Day view)
   │  driver.dump()  →  accessibility XML
   ▼
waits.dump_full_timeline  ──►  richest stable dump for the day
   │
   ▼
parser.parse_day  ──►  DayTimeline (pydantic)
   │
   ▼
pipeline.scrape loop  ──►  data/runs/<stamp>/raw/timeline.jsonl
   │                         data/runs/<stamp>/raw/export.json   (optional, import / --export)
   │  normalize (merge.build_dataset: scrape, export, or both merged;
   │             with an export, every run's timeline.jsonl via history.load_history)
   ▼
data/runs/<stamp>/clean/timeline.{csv,parquet}
   │  stats (optional)
   ▼
console summary
```

### Versioned runs

Each default scrape creates a timestamped folder under `data/runs/` (see
`paths.py`). The marker file `data/latest` records the most recent run so
`normalize` and `stats` can resolve paths without explicit arguments.

```text
data/runs/2026-06-16_143022/
├── raw/
│   ├── timeline.jsonl
│   └── debug/          # failure artifacts (XML + PNG, traceback .txt on device errors)
└── clean/
    ├── timeline.csv
    └── timeline.parquet
```

## Layered design

**Guiding rule:** the driver is "dumb" (dump, tap, swipe, screenshot). **All
intelligence operates on the XML.** Both drivers (uiautomator2 and raw ADB) are
interchangeable; parsing is testable offline with saved dumps.

| Module         | Layer           | Responsibility                                                                                                                                                             |
|----------------|-----------------|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `cli.py`       | CLI             | Typer commands: `run`, `scrape`, `normalize`, `import`, `stats`, `parse-file`, `dump`. Thin wiring only.                                                                   |
| `paths.py`     | I/O layout      | Versioned run directories (and their creation date), `data/latest` marker, listing every run's raw JSONL, default path resolution, copying the official export into a run. |
| `pipeline.py`  | Orchestration   | Day-by-day loop (full capture or step-over), date-drift checks, JSONL append, debug capture on failure, progress lines, graceful stop on Ctrl+C / device errors.           |
| `device.py`    | Transport       | `Driver` protocol: `U2Driver` (primary) and `AdbRawDriver` (fallback). `make_driver()` picks one.                                                                          |
| `navigator.py` | Navigation      | Read the English date header; tap "Día anterior". Date arithmetic is the source of truth; the header **verifies** navigation.                                              |
| `waits.py`     | Synchronization | Stable-screen waits, panel expansion, scroll-to-top after day changes, `dump_full_timeline()`.                                                                             |
| `scroll.py`    | Gestures        | Compute swipe lanes from segment button bounds; expand collapsed bottom sheet.                                                                                             |
| `parser.py`    | Parsing         | Pure: XML string → `DayTimeline`. Never touches the device.                                                                                                                |
| `normalize.py` | Normalization   | JSONL → pandas DataFrame → CSV + Parquet.                                                                                                                                  |
| `official.py`  | Parsing         | Pure: official Timeline export JSON → `OfficialSegment` list (visits, activities).                                                                                         |
| `history.py`   | Normalization   | Read every run's raw JSONL into one scrape history: latest capture per day, and which captures are complete.                                                               |
| `merge.py`     | Normalization   | Align scraped entries with official segments, propagate names by place ID, keep the place-name cache, build the merged dataset from the scrape history.                    |
| `planner.py`   | Planning        | Pure: from the official export, known names and captured days, choose which days to capture (`ScrapePlan`).                                                                |
| `geocode.py`   | Enrichment      | Optional Nominatim geocoder with disk cache and rate limiting.                                                                                                             |
| `stats.py`     | Reporting       | Pure functions over a DataFrame → console summary.                                                                                                                         |
| `models.py`    | Domain          | Pydantic models and enums (`SegmentType`, `TimeAnchor`, `OfficialSegmentKind`).                                                                                            |

### Dependency direction

```text
cli → pipeline, merge, official, planner, stats, paths, device, geocode
pipeline → navigator, parser, waits, device, models
waits → scroll, parser, device
navigator → device, parser (header helpers)
merge → history, normalize, official, models
history → normalize, paths
official → models
planner → models
normalize → geocode (optional)
```

Nothing in `parser`, `models`, `official`, `planner`, `history`, `merge`, `normalize`,
`stats`, or `geocode` imports device code. That boundary is what keeps offline tests fast and reliable.

## Scraping loop (pipeline)

For each requested day, `pipeline.scrape()`:

1. **Expand panel** — `ensure_timeline_panel_expanded()` swipes the bottom sheet
   up if the day list is collapsed (`timeline_panel_needs_expand`).
2. **Capture dump** — `dump_full_timeline()` waits for a stable screen, scrolls
   the list to the top when needed, and may take several swipes to collect the
   richest dump (more segments visible in bounds).
3. **Validate screen** — aborts with debug artifacts if:
   - the expected date ≠ displayed header (date drift),
   - the Timeline day list is not present,
   - the panel is still collapsed.
4. **Parse** — `parse_day(dump, current_date)` → `DayTimeline`.
5. **Cross-check** — logs a warning when segment count ≠ on-screen visit summary
   (`summary_matches()`); saves debug XML when summary shows visits but parser
   found zero segments.
6. **Append JSONL** — one line per day (`timeline.model_dump()`).
7. **Navigate** — tap "Día anterior"; `wait_for_stable_screen()` until two
   consecutive dumps hash identically; advance `expected` date by −1 day.

Navigation failures capture a screenshot and honor `--on-error skip|abort`.

**Stopping early.** Ctrl+C (`KeyboardInterrupt`) or any exception raised while walking
(lost USB / adb connection, uiautomator2 or app errors) ends the loop instead of the
process: the traceback goes to `debug/{date}_error.txt`, `ScrapeResult.stopped` records
why, and the CLI still merges the days already appended to the JSONL. Each day is
written as soon as it is parsed, so nothing captured is lost.

### Planned walk (`--export` without `--days`)

Before planning, the CLI loads the **scrape history** (`history.load_history` over every
run's `raw/timeline.jsonl`) and learns the names it already teaches
(`merge.learned_so_far`: history matched to the export, plus `data/cache/places.json`).
`planner.plan_scrape()` then turns the official export into a `ScrapePlan`:

1. Collect visits up to the start day (`--until`, today by default) whose place ID has
   no known name.
2. Drop days the history captured **completely** (the run started after the day ended):
   they are never planned again. Each one counts as an attempt for the unnamed places it
   shows; after `MAX_ATTEMPTS` (2), or with no uncaptured day left, a place is skipped.
3. Target every place left, or with `--since` only those with an uncaptured visit on or
   after that day. Each place only needs its most recent such day; the oldest of those
   is how far the walk must go.
4. Always add the days the export does not reach (from its last day to the start day,
   minus complete captures and days before `--since`), then pick the fewest extra days that show every chosen place
   (greedy set cover seeded with those days, ties to the more recent day).

`ScrapePlan.describe()` prints the plan (counts and ISO dates only), a tip when the newest
planned day is `TIP_MIN_DAYS` (7) or more back (opening the Timeline there skips the newer
days), and how many places were skipped.

`pipeline.scrape(only_days=plan.days)` then walks back as usual, but days outside the
plan are only **stepped over**: the stable dump left by the previous tap is reused to
verify the header date and find "Día anterior" (no panel expansion, scrolling, or
parsing). The loop stops once it is past the oldest planned day. The start day is always
read in full once, because its date is not known before the first dump; planned days
newer than it are reported as unreachable. Every `PROGRESS_EVERY` (25) days a progress
line shows walked / captured counts and an estimate of the time left.

## Why scraping the UI works

Non-obvious details about the Google Maps Timeline UI:

### WebView + Button nodes

The Timeline is rendered in a **WebView**. Each entry (visit, trip leg, etc.) is
an `android.widget.Button`. Text is **not** in the `text` attribute — it lives
in **`content-desc`** (accessibility description).

### Full day without scrolling

Off-screen entries still appear in the XML with empty bounds (`[0,0][0,0]`) while
their `content-desc` is fully populated. The parser can read an entire day from
one dump. Scrolling is still used to:

- expand a collapsed bottom sheet,
- reset list position after changing days,
- prefer dumps where more segments have non-zero bounds (richer dump selection).

### Document order is chronological

Node order in the XML matches the chronological order of events during the day.

### Field separator vs. decimals

Inside a `content-desc`, fields are separated by `", "` (comma + space), while
decimals use a comma with no space (`"2,4 km"`). Splitting on `", "` is safe.

### Mixed-language UI

The **date header is in English** ("Sat Jun 6, 2026", "Today", "Yesterday")
even when segment text is in **Spanish** ("En automóvil", "¿Visitaste …?").
Navigation uses the Spanish accessibility label `"Día anterior"` for the
previous-day button.

The summary bar (e.g. `"5 visitas"`) is parsed separately and cross-checked
against parsed visit counts.

### Map canvas has no readable nodes

The map itself is a `SurfaceView` — a graphical canvas with no useful
accessibility text. Coordinates are **not** available from scraping; use
`--geocode` during normalization if you need `lat`/`lon`.

## Merging with the official export

`merge.build_dataset()` dispatches: scrape only → `normalize()` (unchanged output);
export present → `merge_rows()` over the scrape history (the run's own JSONL plus every
other run's, latest capture per day):

1. **Parse** the export (`official.py`): keep `semanticSegments` visits and activities,
   with timezone-aware times; ignore `timelinePath`, `rawSignals`, `userLocationProfile`.
2. **Intervals.** Each scraped entry becomes a local wall-clock interval: `range` as
   shown (wrapping past midnight if needed), `departure` = midnight → time,
   `arrival` = time → midnight, `all_day` = the whole day. Official intervals drop the
   UTC offset and are truncated to minutes, like the app's clock.
3. **Candidates.** For each scraped entry, score official segments of the same kind that
   touch that day (clipped to the day, widened to fit the entry) by intersection over
   union; keep scores ≥ `MIN_MATCH_SCORE` (0.5).
4. **Assignment.** Greedy by score: each scraped entry is used once, each official
   segment once **per day** (a visit across midnight takes the arrival entry of one day
   and the departure entry of the next).
5. **Propagation.** The most common scraped `(title, address)` per place ID names every
   other visit to that place, on top of the names cached from earlier runs (fresh names
   win; the cache is rewritten after each merge). The most common scraped label per
   activity type names unmatched trips (falling back to the raw type, e.g. `IN_BUS`).
6. **Rows.** One row per official segment (official times, distances, coordinates; UI
   type, name, `confirmed`, `needs_user_action`) plus one row per unmatched scraped entry.

The console report prints counts only (matched entries, named visits), never names or
coordinates.

## Segment classification

The parser classifies each `content-desc` into a `SegmentType`:

| Type                | Meaning             | Example start of `content-desc`    |
|---------------------|---------------------|------------------------------------|
| `place_visit`       | Confirmed visit     | `"Cafe Ejemplo"`, `"C. 12 3456"`   |
| `activity`          | Trip between places | `"En automóvil · 2,4 km · 10 min"` |
| `unconfirmed_visit` | Confirmation prompt | `"¿Visitaste …?"`                  |
| `unknown_visit`     | Unidentified place  | `"Visita desconocida"`             |
| `missing_transit`   | Missing travel mode | `"Modo de viaje faltante"`         |

`needs_user_action` is `true` for the last three categories so analysts can
filter low-confidence rows.

## Stable-screen waits

Instead of fixed `sleep()` durations, `wait_for_stable_screen()` polls dumps
until **two consecutive XML hashes match**, indicating the transition animation
finished. A short settle delay follows before returning the final dump.

## Driver selection

`make_driver(serial, prefer)`:

- **`prefer=u2` (default):** `U2Driver` via uiautomator2. Installs a helper APK
  on first connect; generally more reliable for taps and dumps.
- **`prefer=adb`:** `AdbRawDriver` using `adb shell uiautomator dump` and
  `input tap/swipe`. Useful when uiautomator2 cannot connect; only requires
  the `adb` binary.

Both implement the same `Driver` protocol so upper layers are unaware of which
backend is active.

## Geocoding (optional)

See [`DATA.md`](DATA.md#geocoding). Implemented in `geocode.py` as a pure HTTP
client to Nominatim with:

- on-disk cache (`data/cache/geocode.json`),
- 1 request/second throttle,
- graceful degradation (missing network → empty `lat`/`lon`, normalization still
  succeeds).

## Reliability checklist

| Mechanism              | Where                           | Purpose                                                                     |
|------------------------|---------------------------------|-----------------------------------------------------------------------------|
| Date-drift guard       | `pipeline.py`                   | Stop if arithmetic date ≠ header date                                       |
| Stable-screen wait     | `waits.py`                      | Never parse mid-transition                                                  |
| Summary cross-check    | `DayTimeline.summary_matches()` | Detect parser regressions                                                   |
| Debug artifacts        | `pipeline.py` → `raw/debug/`    | XML + PNG for failed days                                                   |
| Richest-dump selection | `waits.dump_full_timeline()`    | Prefer dumps with more in-bounds segments                                   |
| Panel expansion        | `scroll.py` + `waits.py`        | Recover from collapsed sheet                                                |
| `on_error` policy      | `pipeline.py`                   | `skip` failed days vs `abort` entire run                                    |
| Graceful stop          | `pipeline.py`                   | Ctrl+C / device errors end the walk; captured days are kept and merged      |
| Scrape history         | `history.py` + `planner.py`     | Resume long walks: days captured by any run are reused, not walked to again |

## Testing strategy

Tests live under `tests/`, one file per module, with shared fixtures in
`conftest.py` (`FakeDriver`, synthetic XML builders, sample JSONL).

- **Parser / normalize / official / planner / merge / stats / models:** pure functions, no I/O.
- **History / paths:** temporary run folders (`write_run_scrape`); every test points
  `data/runs/`, `data/latest` and the place-name cache at `tmp_path` (autouse fixtures).
- **Pipeline / navigator / waits / scroll:** `FakeDriver` or saved XML strings.
- **Device:** subprocess mocks for `adb` calls.
- **Geocode:** HTTP mocked.

Coverage is enforced at **100% line and branch** on `maps_timeline/`. See
[`DEVELOPMENT.md`](DEVELOPMENT.md).

## Extending the tool

| Change                                 | Touch                     | Offline test                                    |
|----------------------------------------|---------------------------|-------------------------------------------------|
| New segment type or UI string          | `parser.py`, `models.py`  | `parse-file` on new dump                        |
| New CLI flag                           | `cli.py` + target module  | `tests/test_cli.py`                             |
| Different output columns               | `normalize.py`            | `tests/test_normalize.py` + re-run on JSONL     |
| New wait/heuristic                     | `waits.py`, `scroll.py`   | unit tests with synthetic XML                   |
| Path layout                            | `paths.py`                | `tests/test_paths.py`                           |
| Official export field or matching rule | `official.py`, `merge.py` | `tests/test_official.py`, `tests/test_merge.py` |
| Planning rule (which days to capture)  | `planner.py`              | `tests/test_planner.py`                         |

Preserve **raw JSONL compatibility** when changing `models.py` field names or
structure, or document the breaking change explicitly.
