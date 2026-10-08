---
description: Hard constraints on the scraper, the phone it drives and the location data it handles
---

# Rules: scraper guardrails

maps-timeline drives a real phone and handles a person's location history. These constraints keep
both safe, and keep every capture ever made usable. Each section cites the ADR that holds the
rationale.

## Location data: [ADR-0007](../../docs/adr/0007-location-data-never-leaves-the-users-machine.md)

- NEVER commit, upload, paste or attach real user data: anything under `data/`, an official
  export (`Timeline.json`, `raw/export.json`), XML dumps or screenshots from a real phone. `data/`,
  `dump*.xml` and `*.png` are git-ignored; keep them that way. The repository is public.
- Tests, docs, issues and pull requests use synthetic data. A real dump is anonymized (place
  names, addresses) before it leaves the machine, and is described as anonymized.
- CLI messages print counts, not place names, addresses or coordinates, unless the message exists
  to show them (`stats`, `parse-file`).
- The network is opt-in: only `--geocode` sends addresses, to Nominatim.
- No device serials, tokens or personal paths in code; they come from options or the environment.

## The phone: [ADR-0001](../../docs/adr/0001-the-scraper-reads-the-timeline-from-the-accessibility-tree.md)

- Read the screen and navigate, nothing else: dumps, screenshots, taps and swipes on the Google
  Maps UI.
- NEVER run destructive adb commands (uninstall, clear data, reboot, change settings, delete
  files) or install apps without explicit approval. uiautomator2 installs its own helper on first
  use; nothing else does.
- A live run needs the person: they connect the phone and open Maps on Rutas → Día. Agents do not
  start a scrape on their own.

## Layers: [ADR-0003](../../docs/adr/0003-parsing-works-on-the-xml-never-on-the-device.md)

- Interpretation (finding nodes, classifying segments, reading dates) works on the XML dump, in
  pure functions. The drivers in `device.py` stay dumb and interchangeable (uiautomator2 or raw
  adb).
- `parser.py`, `official.py`, `planner.py` and `stats.py` are pure. `merge.py` only reads and
  writes files around pure logic. Transport, parsing and normalization never mix.
- New scraping logic is testable offline, with a synthetic or anonymized dump (`parse-file`).
- `cli.py` stays thin: it parses options, delegates and prints.
- The Spanish strings the app renders (`"Día anterior"`, `"En automóvil"`, `"¿Visitaste"`) are
  selectors: never translate them.

## Navigation: [ADR-0004](../../docs/adr/0004-the-day-comes-from-date-arithmetic-the-header-only-verifies-it.md)

- The walked day comes from date arithmetic; the header only verifies it. A mismatch stops the
  walk; it is never resolved by trusting the header.
- A missing "Día anterior" button follows the `on_error` policy: `skip` records the failed day and
  goes on, `abort` stops.
- Ctrl+C or a device error ends the walk and keeps the days already captured.

## Captured data stays usable: [ADR-0002](../../docs/adr/0002-raw-capture-and-normalization-are-separate-stages.md), [ADR-0006](../../docs/adr/0006-the-official-export-plans-the-walk-and-every-run-counts.md)

- The raw JSONL is a contract: every run ever captured must still normalize. A change to
  `models.py` stays compatible with the JSONL already written, or the pull request documents the
  break in `docs/DATA.md` and marks it breaking.
- Commands, options and output columns change only additively, unless the pull request says it
  breaks them.
- A day captured completely by any run is never planned again, and the latest capture of a day
  wins.
