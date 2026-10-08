# 0004. The day comes from date arithmetic; the header only verifies it

**Status:** Accepted · **Date:** 2026-10-08

## Context

The scraper walks backwards: capture the displayed day, tap "Día anterior", wait for the screen to
settle, repeat. Every captured entry is stored under a date, and a wrong date silently corrupts the
dataset: the entries of one day filed under another.

The screen shows the date in a header, in English and in more than one shape: "Today",
"Yesterday", or "Sat Jun 6, 2026". Relative headers depend on the reference day, and a header can
be missing from a dump taken mid-transition. A tap can also fail to land, or land twice.

## Options

- **Trust the header on every day:** simple, but a missing or unparseable header leaves the day
  without a date, and a skipped or doubled tap goes unnoticed because every header looks valid.
- **Count taps only:** the date is the start day minus the number of taps, with no check, so one
  lost tap shifts every later day.
- **Arithmetic as the source of truth, header as the check:** the expected day is computed, and
  the header must agree with it; a disagreement stops the walk.

## Decision

- The first dump anchors the walk: its header date (or today, if it cannot be read) is the first
  expected day. After each successful tap the expected day moves back by exactly one day.
- Each dump's header is parsed (`navigator.resolve_header_date`) and compared with the expected
  day. A mismatch is date drift: the walk stops, records the day as failed and keeps what it
  already wrote. A header that cannot be read falls back to the expected day.
- A missing previous-day button is a navigation failure: a screenshot goes to `raw/debug/` and the
  `--on-error` policy decides between `skip` (the default: record the day as failed and continue)
  and `abort`.
- The same check runs on days that are only stepped over in a planned walk
  ([ADR-0006](0006-the-official-export-plans-the-walk-and-every-run-counts.md)): the dump left by
  the previous tap is reused to read the header before tapping again.

## Consequences

### Positive

- A lost or doubled tap stops the walk at the first wrong day instead of mislabeling every day
  after it.
- Relative headers ("Today", "Yesterday") and missing headers do not decide the date on their own.

### Negative / trade-offs

- Drift always stops the walk, whatever `--on-error` says; resuming means running again
  (a planned walk resumes where it stopped).
- The header format is a selector like any other: if the app changes it, verification degrades to
  the arithmetic alone until the parser is updated.

### Follow-ups

- `.agents/rules/scraper-guardrails.md` cites this ADR for navigation.
- `docs/ARCHITECTURE.md` (*Scraping loop*) describes the loop step by step.
