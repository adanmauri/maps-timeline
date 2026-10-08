# 0007. Location data never leaves the user's machine

**Status:** Accepted · **Date:** 2026-10-08

## Context

Everything this tool handles is location history: where a person was, when, for how long, with
names and addresses from the app and coordinates from the official export. The export file also
holds raw GPS fixes and nearby Wi-Fi scans. The repository is public, and the tool runs on the
user's own computer against the user's own phone.

The data passes through several places where it could leak: run folders, the place-name and
geocoding caches, debug artifacts (XML dumps and screenshots of real days), console output, test
fixtures, issues, pull requests and commits.

## Options

- **Rely on care case by case:** no constraints, and one careless commit or log line publishes a
  history that cannot be taken back.
- **Keep every artifact local by construction:** a single gitignored folder for data, synthetic
  test data, counts-only output, and no network calls unless the user asks for one.

## Decision

- **One local folder.** Runs, caches and drafts live under `data/`, which is gitignored, as are
  `dump*.xml` and `*.png`. Nothing under it is committed, uploaded or pasted into an issue or pull
  request unless the user explicitly asks.
- **Synthetic test data.** Fixtures are built in `tests/conftest.py` (synthetic XML, JSONL and
  export payloads); tests never use a real export or a real dump. Every test runs against a
  temporary `data/` (autouse fixtures), so tests never read or write the real one.
- **Counts-only output.** Console messages and reports print counts, ISO dates and file paths,
  never place names, addresses or coordinates, unless that output is the point of the command
  (`stats`, `parse-file`).
- **No network by default.** No Google API is called. Geocoding through Nominatim is opt-in
  (`--geocode`), sends only scraped addresses, honors its usage policy (1 request per second, a
  contact in the User-Agent) and caches results in `data/cache/geocode.json`.
- **The phone is only read.** The scraper dumps the screen, taps and swipes to navigate; it never
  runs destructive `adb` commands, changes settings or installs apps beyond the helper uiautomator2
  installs itself on first connect.
- No credentials, device serials or personal paths in the code; they come from CLI options.

## Consequences

### Positive

- A clone of the repository, its CI logs and its issues hold no location history.
- Bug reports can be reproduced from anonymized dumps without sharing real days.

### Negative / trade-offs

- Real-device problems need an anonymized dump or a description, which is slower to act on than
  the real file.
- Counts-only output is less helpful when debugging a wrong match; the data has to be inspected
  locally.
- Deleting `data/` is the only way to forget, and it also drops the caches.

### Follow-ups

- `.agents/rules/scraper-guardrails.md` cites this ADR for privacy and device use.
- The README's *Privacy* section and `docs/DATA.md` tell users what each file contains.
