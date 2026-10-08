# AI Agents Guidelines

## Overview

This document defines the operating principles, execution protocols, and
guardrails for AI agents working on the **maps-timeline (`maps_timeline`)**
project. The goal is to keep assistance consistent, secure, and useful while
preserving code quality and project standards.

### Project Context

`maps_timeline` is a command-line tool written in **Python 3.13** that extracts
the **location history (Routes/Timeline) from Google Maps** on an Android phone,
reading the accessibility hierarchy (`uiautomator` XML dump) over **ADB**.

The core idea is a **two-stage, decoupled design**:

1. **Scraping (raw data)**: walks the Timeline day by day, going backwards, and
   saves each day exactly as it appears on screen into a raw JSONL file. It does
   not interpret numbers or dates: it only captures text.
2. **Normalization**: converts the raw JSONL into a clean dataset (CSV +
   Parquet), parsing durations, distances, and times into numeric / ISO types.

Splitting the two stages makes it possible to **reprocess** the raw data (for
example, when improving the parser) without having to re-scan the phone.

Stage 2 accepts an optional second raw input: the **official on-device Timeline
export** that Android saves from its settings (`raw/export.json`). It has coordinates
and Google place IDs but no names; `merge.py` aligns it with the scrape by time and
propagates scraped names to every visit with the same place ID. The export can also
drive stage 1: `planner.py` picks only the days that show still-unnamed places, and the
scraper steps over the rest. With an export, every run's raw JSONL counts
(`history.py`): days captured by any run are merged into the dataset and never planned
again, so an interrupted walk resumes instead of starting over.

The code (docstrings, comments, and CLI messages) is written in **English**,
which is the project's language. The only Spanish strings allowed in the code are
**UI selectors / regexes that must match the Google Maps app**, which renders in
Spanish (e.g. `"Día anterior"`, `"En automóvil"`, `"¿Visitaste"`); these must not
be translated.

### Project Structure

```
.
├── maps_timeline/
│   ├── __init__.py      # package version
│   ├── cli.py           # command-line interface (typer): run, scrape, normalize, import, stats, parse-file, dump
│   ├── device.py        # transport layer: Driver (Protocol), U2Driver, AdbRawDriver, make_driver
│   ├── navigator.py     # navigation: read the header date and step back one day
│   ├── parser.py        # pure parsing of the XML dump -> DayTimeline (testable with saved dumps)
│   ├── pipeline.py      # orchestrates the sequential scraping loop and writes the raw JSONL
│   ├── paths.py         # versioned run dirs under data/runs/, data/latest marker
│   ├── scroll.py        # Timeline list swipe gestures from segment bounds
│   ├── waits.py         # explicit waits, panel expansion, dump_full_timeline
│   ├── normalize.py     # raw JSONL -> DataFrame -> CSV + Parquet (pandas)
│   ├── official.py      # pure parsing of the official on-device Timeline export (JSON)
│   ├── history.py       # every run's raw JSONL as one scrape history (latest capture per day)
│   ├── merge.py         # align scrape + official export, propagate names, build dataset
│   ├── planner.py       # pure: choose which days to capture from the official export
│   ├── geocode.py       # optional: NominatimGeocoder (addresses -> lat/lon, cached)
│   ├── stats.py         # console summary over the clean DataFrame
│   └── models.py        # domain models (pydantic): Segment, DayTimeline, OfficialSegment, enums
├── data/                # gitignored — sensitive exports (see docs/DATA.md)
│   ├── latest           # pointer to most recent run
│   ├── cache/           # geocode.json (Nominatim), places.json (place ID -> learned name)
│   └── runs/<stamp>/    # raw/timeline.jsonl (+ raw/export.json) + clean/timeline.{csv,parquet}
├── docs/                # ARCHITECTURE, CLI, DATA, DEVELOPMENT guides
├── tests/               # one test file per module + conftest.py
├── dump_*.xml           # sample XML dumps for offline testing (parse-file)
├── pyproject.toml       # metadata, dependencies, and the `maps-timeline` script
├── uv.lock              # reproducible lockfile (UV)
├── Makefile             # install, quality, CLI shortcuts
├── README.md
└── AGENTS.md
```

### Architecture and Layers

The project follows a strict separation of concerns so that logic is testable
without a connected phone:

| Layer | Module | Responsibility |
| --- | --- | --- |
| CLI | `cli.py` | Command definitions (typer), option parsing, user output. Must be thin and delegate to the other layers. |
| I/O layout | `paths.py` | Versioned `data/runs/<stamp>/` folders, `data/latest` marker, default path resolution for CLI. |
| Transport | `device.py` | Talk to the device: `dump()`, `tap_xy()`, `swipe()`, `screenshot()`. A "dumb", interchangeable driver (uiautomator2 ↔ raw ADB). |
| Navigation | `navigator.py` | Read the displayed date and tap "Previous day". The source of truth for the day is date arithmetic; the header only **verifies** it. |
| Gestures | `scroll.py` | Compute swipe lanes from segment button bounds; expand collapsed Timeline panel. |
| Waits | `waits.py` | Stable-screen waits, `dump_full_timeline()`, panel expansion orchestration. |
| Parsing | `parser.py` | Convert the XML into a `DayTimeline`. **Pure function**: operates on the XML, never touches the device. |
| Orchestration | `pipeline.py` | Day-by-day scraping loop (capture or step over), date-drift checks, debug artifacts, progress lines, and writing the raw JSONL. Ctrl+C / device errors end the walk but keep the captured days. |
| Normalization | `normalize.py` | Flatten the JSONL into a DataFrame and write CSV + Parquet; optionally add lat/lon via a geocoder. |
| Official export | `official.py` | **Pure** parsing of the official on-device Timeline export (`semanticSegments` visits and activities) into `OfficialSegment` models. |
| History | `history.py` | Read every run's raw JSONL into one scrape history: the latest capture of each day and which captures are complete (taken after the day ended). |
| Merge | `merge.py` | Align scraped entries with official segments by time overlap, propagate names by place ID (plus the place-name cache), and build the merged dataset. Pure apart from reading/writing files. |
| Planning | `planner.py` | **Pure**: from the official export, already-known names and already-captured days, choose the days to capture (`ScrapePlan`) so `pipeline.scrape(only_days=...)` steps over the rest. |
| Geocoding | `geocode.py` | Optional post-processing: resolve addresses to lat/lon via Nominatim (OpenStreetMap), with caching and rate limiting. Pure HTTP, no device access. |
| Reporting | `stats.py` | Console summary (totals, top places) from the clean DataFrame. Pure functions, no device access. |
| Models | `models.py` | Domain structures (pydantic) and enums (`SegmentType`, `TimeAnchor`, `OfficialSegmentKind`). |

**Key principle**: all the intelligence (finding nodes, classifying segments,
reading dates) operates **on the XML**, not on the device. This keeps the
drivers (uiautomator2 and raw ADB) interchangeable and lets the logic be tested
with the same saved dumps.

### Data Flow

```
Phone (Google Maps, "Routes" screen)
   │  driver.dump()  (accessibility XML)
   ▼
pipeline.scrape  ──parse_day──►  DayTimeline (pydantic)
   │
   ▼
data/runs/<stamp>/raw/timeline.jsonl   (one day per line, raw data)
data/runs/<stamp>/raw/export.json      (optional: official Timeline export, verbatim)
   │  normalize / import  (merge.build_dataset; with an export, every run's JSONL)
   ▼
data/runs/<stamp>/clean/timeline.csv  +  timeline.parquet  (clean dataset)
   │  stats (optional)
   ▼
console summary
```

## Core Principles

### 1. Decoupled, Testable Design

- Keep parsing as **pure functions** over XML, with no I/O side effects or device
  calls.
- Any new scraping logic must be testable **offline** with a saved XML dump (see
  the `parse-file` command).
- Do not mix transport (ADB/uiautomator2) with parsing or normalization.

### 2. Security and Privacy

- **Sensitive personal data**: the Timeline contains location history. Never
  upload, expose, or commit real user data (contents of `data/`, XML dumps with
  real addresses) unless explicitly requested.
- **No hardcoded credentials**: do not embed device serials, tokens, or private
  paths in the code; use CLI options / environment variables.
- **Do not modify the device**: the scraper only reads the screen and navigates
  (UI taps/swipes). Never run destructive ADB commands or install / uninstall
  apps without explicit authorization.

### 3. Code Quality Standards

- **Type hints** on all function and method signatures.
- **Pydantic** for domain models.
- Clear error handling with descriptive messages.
- Clear docstrings (see the format below).

## Code Quality Standards

### Language and Communication

- **Comments, docstrings, and CLI messages in English** (the project's
  language). Keep Spanish only for UI selectors/regexes that must match the
  Google Maps app (it renders in Spanish); never translate those.
- **Logs / outputs must not rely on emojis** to convey information; the existing
  decorative emojis in CLI messages (`[✓]`, `[!]`, `[·]`) may be kept for
  consistency, but the message must be readable without them.
- Clear, actionable error messages (what happened and what to do).

### Python Version and Type Hints

- **Python 3.13+ syntax is required.**
- Use `from __future__ import annotations` (already present in the modules).
- Use built-in types instead of the `typing` module when possible:
  - `dict` instead of `typing.Dict`
  - `list` instead of `typing.List`
  - `tuple` instead of `typing.Tuple`
  - `set` instead of `typing.Set`
- Prefer union syntax:
  - `type | None` instead of `Optional[type]` (e.g. `str | None`)
  - `type1 | type2` instead of `Union[type1, type2]`
- Import from `typing` / `collections.abc` only what is needed (e.g. `Any`,
  `Protocol`, `Callable`, `cast`, `TYPE_CHECKING`, `Literal`). Do not import
  `Optional`, `Dict`, `List`, `Tuple`, `Set`, or `Union`.

**Examples:**

```python
# Correct (Python 3.13+)
def parse_segment(desc: str) -> Segment | None:
    ...

def make_driver(serial: str | None = None, prefer: str = "u2") -> Driver:
    ...
```

### Docstring Format

Every **module**, **class**, and **function/method** (including private `_`
helpers and test functions) must have a docstring:

- **Modules**: opening docstring describing the purpose; may be multi-line when
  it adds context (UI findings, design decisions).
- **Classes**: brief docstring explaining the responsibility.
- **Functions/methods**: single-line docstring by default; multi-line only if it
  exceeds ~100 characters or needs to list structured information.
- Do not include "Args:", "Returns:", or "Parameters:" sections.
- No blank line between the docstring and the first line of code in a function.

### Code Style

- Follow PEP 8.
- Target line length: 100.
- Descriptive variable and function names.
- Prefer explicit over implicit code.
- "Private" helper functions / internals use the `_` prefix (e.g. `_classify`,
  `_parse_time`, `_iter_button_descs`).

### Imports

- Group: standard library, third-party, local.
- Use relative imports within the `maps_timeline` package (e.g.
  `from .parser import parse_day`).
- Heavy or device-dependent imports (e.g. `uiautomator2`) may be deferred inside
  the function so they do not penalize CLI startup or offline flows (a pattern
  already used in `cli.py` and `device.py`).

### Error Handling

- Use specific exception types when possible
- Include descriptive error messages in English
- Use `ValueError` for invalid input
- Use `FileNotFoundError` for missing files
- Use `NotImplementedError` for abstract methods
- Use specific exception types when possible.
- `RuntimeError` for device connection failures (already used in `make_driver`).
- In the scraping loop, navigation failures must honor the `on_error` policy
  (`skip` vs `abort`) and record the failed day, without aborting the whole
  process unless requested.

### Linting and Suppressions

- **Fix the code first.** Prefer refactoring, tighter types, or clearer structure
  over silencing a linter or type checker.
- **Do not hide diagnostics in `pyproject.toml`** except for ecosystem-wide
  incompatibilities that cannot be expressed per line:
  - `flake8` `E203` / `W503` when using `black` as the formatter.
  - `ruff` `E501` when `black` owns line wrapping.
  - `mypy` `ignore_missing_imports` for third-party modules that ship no stubs
    (currently `uiautomator2`, `pyarrow`).
- **Inline suppressions only on the offending line**, with a short reason when
  it is not obvious:
  - `# pylint: disable=import-outside-toplevel` on deferred imports in `cli.py`
    and `device.py` (startup cost).
  - `# nosec B603` on fixed-argv `subprocess.run(...)` calls in `device.py`.
  - `# nosec B405` / `# nosec B314` on `xml.etree` usage (trusted local adb /
    saved dumps, not arbitrary network XML).
  - `# pylint: disable=unnecessary-ellipsis` on `...` stubs inside `typing.Protocol`
    bodies (required by pyright; docstrings must still be present).
  - `# noqa: B904` / `# type: ignore[...]` only when the checker is wrong and
    there is no clean alternative.
- **Typer CLI options**: use `typing.Annotated[..., typer.Option(...)]` instead
  of `# noqa` for `ruff` rule `B008`.
- **`bandit`** scans `maps_timeline` only (`make security`); tests intentionally
  use `assert` and are out of scope.
- Run **`make quality && make test`** before finishing a change (or the
  individual targets below). **`make quality` does not run tests.**

| Target | What it runs |
| --- | --- |
| `make quality` | `lint` + `type-check` + `security` (ruff, flake8, pylint, mypy, pyright, bandit) |
| `make test` | pytest with **100%** line/branch coverage on `maps_timeline/` |
| `make lint` / `make type-check` / `make security` | Subset of `make quality` |

## Dependency Management

- **Use UV** (`pyproject.toml` + `uv.lock`).
- Production dependencies in `[project.dependencies]`, with minimum/compatible
  version constraints; exact versions are pinned by `uv.lock`.
- Keep dependencies **alphabetically sorted**.
- Add packages with `uv add <pkg>` (and `uv add --dev <pkg>` for development
  tools); never hand-edit the lockfile.
- Commit `uv.lock` for reproducible builds.
- Current dependencies: `pandas`, `pyarrow`, `pydantic`, `requests`, `tenacity`,
  `typer`, `uiautomator2`.

## CLI Usage

The project exposes the `maps-timeline` command (defined in `[project.scripts]`).
Full option reference: `docs/CLI.md`.

```bash
# Scrape + normalize + summary (recommended)
uv run maps-timeline run --days 3

# Walk the Timeline day by day and save the raw JSONL
uv run maps-timeline scrape --days 3

# Convert the raw JSONL (and raw/export.json, if present) into CSV + Parquet
uv run maps-timeline normalize

# Import the official on-device Timeline export (new run, or --run to merge with a scrape)
uv run maps-timeline import Timeline.json

# Let the official export plan the walk (captures only days with unnamed places)
uv run maps-timeline run --export Timeline.json
# (Ctrl+C keeps what was captured; run it again to continue where the plan left off)

# Print a console summary of the clean dataset
uv run maps-timeline stats

# Convert and also geocode addresses to lat/lon (Nominatim / OpenStreetMap)
uv run maps-timeline normalize --geocode --nominatim-email you@example.com

# Offline test: parse a saved XML dump (no phone required)
uv run maps-timeline parse-file dump_dia.xml

# Take a single dump of the current screen (to calibrate selectors)
uv run maps-timeline dump --out dump.xml
```

**Requirements for live scraping**: an Android phone with USB debugging
enabled, `adb` available, and Google Maps open on the **Routes** screen ("Day"
view) before running `scrape`.

## Execution Protocols

### 1. Before Implementing

1. **Identify the layer** involved (CLI → transport → navigation → parsing →
   orchestration → normalization → models) and respect its responsibilities.
2. **Verify dependencies** and configuration.
3. **Assess the impact** on the raw → clean data flow.
4. **Plan the offline test** with saved dumps where applicable.

### 2. Implementation Guidelines

- Respect the existing structure and patterns.
- Keep the CLI thin: logic lives in the modules, not in the commands.
- Any change to the models (`models.py`) must remain compatible with
  reprocessing the already-generated raw JSONL, or document the incompatibility.

### 3. Quality Assurance

The project uses `make` targets for validation. Before finishing a change:

- Confirm the CLI imports and runs: `uv run maps-timeline --help`.
- Run **`make quality && make test`** — they are separate gates:
  - `make quality` → lint, type-check, security (no pytest).
  - `make test` → pytest with **100% line and branch coverage** on
    `maps_timeline/` (`--cov-fail-under=100`).
- Run the offline parse against a saved dump when parser logic changed:
  `uv run maps-timeline parse-file dump_dia.xml` and check that the segment
  count matches the summary (`summary_matches()`).

Tests live under `tests/`, **one file per module** (`test_parser.py`,
`test_pipeline.py`, …) plus `conftest.py` for shared fixtures (`FakeDriver`,
synthetic XML builders, sample JSONL). Favor **pure functions** and mocked I/O
(device drivers, HTTP geocoding, subprocess) so nothing requires a connected
phone.

Quality tools (dev dependencies): `ruff`, `flake8`, `pylint`, `mypy`,
`pyright`, `bandit`, `black`, `isort`, `pytest`, `pytest-cov`. Configuration
lives in `pyproject.toml`; see **Linting and Suppressions** above for the
policy on global vs inline disables.

## Guardrails and Limitations

### Security

- Do not embed credentials, serials, or personal data in the code.
- Do not upload or expose the contents of `data/` or dumps with real locations.
- Do not run destructive ADB commands or modify the device state beyond the UI
  navigation needed for scraping.

### Operational

- **No breaking changes**: preserve the raw JSONL compatibility and the CLI
  interface.
- **No new external dependencies** without justification; prefer what is already
  in `pyproject.toml`.
- **Documentation inside the repo**: update `README.md`, `docs/`, and this file when
  commands, data flow, or architecture change.

### Data Handling

- Treat location history as **sensitive personal data**.
- Do not log addresses, coordinates, or place names in unnecessary messages.

## Documentation Maintenance

Keep these files in sync when behavior, CLI, schemas, or architecture change:

| File | Purpose |
| --- | --- |
| `README.md` | User-facing overview, quick start, troubleshooting |
| `docs/ARCHITECTURE.md` | Layers, scraping loop, UI findings, reliability |
| `docs/CLI.md` | Complete command and option reference |
| `docs/DATA.md` | JSONL / CSV / Parquet schemas, geocoding |
| `docs/DEVELOPMENT.md` | Contributor setup, `make` targets, testing |
| `docs/README.md` | Documentation index |
| `.agents/skills/` | Project agent skills (branch, PR, issues) — **source of truth** |
| `.cursor/skills/` | Stubs → `.agents/skills/` (Cursor IDE) |
| `.cursor/rules/` | Cursor rules pointing here |
| `.github/` | CI workflows and PR template |
| `AGENTS.md` | This file — agent guardrails and code standards |

Use clear, concise language; include only short snippets when necessary.

---

**Last Updated**: 2026-10-08
**Version**: 2.5
