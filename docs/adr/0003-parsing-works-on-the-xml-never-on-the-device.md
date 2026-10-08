# 0003. Parsing works on the XML, never on the device

**Status:** Accepted · **Date:** 2026-10-08

## Context

Two ways of talking to the phone are available: uiautomator2, a Python library that installs a
helper app on the phone and is generally more reliable for dumps and taps, and the plain `adb`
binary (`adb shell uiautomator dump`, `input tap`, `input swipe`), which needs nothing on the phone
and works when uiautomator2 cannot connect. Both can return the same accessibility XML.

Finding the Timeline entries, classifying them, reading the header date and locating the
previous-day button are the parts that change when the app changes, and the parts that need the
most tests. A test that needs a connected phone cannot run in CI or on a contributor's machine.

## Options

- **Use the driver's own selectors (uiautomator2 queries on the device):** less code, but the logic
  is tied to one driver, the raw ADB fallback would need a second implementation, and tests need a
  phone.
- **Logic on the XML, a minimal driver:** the driver only dumps, taps, swipes and takes
  screenshots; everything else is a function of the XML string. Any driver that can produce the
  dump works, and every rule can be tested with a saved or synthetic dump.

## Decision

- `device.py` defines a `Driver` protocol with `dump()`, `tap_xy()`, `swipe()` and `screenshot()`,
  implemented by `U2Driver` and `AdbRawDriver`. `make_driver()` tries uiautomator2 first (unless
  `--prefer adb`) and falls back to raw ADB.
- `parser.py` is pure: XML string in, `DayTimeline` out. Navigation (`navigator.py`), waits and
  gestures (`waits.py`, `scroll.py`) decide what to do from the XML and only call the driver to
  act.
- Nothing in `parser`, `models`, `official`, `planner`, `history`, `merge`, `normalize`, `stats` or
  `geocode` imports device code.
- Parser changes are checked offline: `maps-timeline parse-file <dump>.xml` on a saved, anonymized
  dump, and unit tests built from synthetic XML (`tests/conftest.py`) with a `FakeDriver` that
  records taps and returns canned dumps.
- The Spanish UI strings in selectors stay untranslated
  ([ADR-0001](0001-the-scraper-reads-the-timeline-from-the-accessibility-tree.md)).

## Consequences

### Positive

- The two drivers are interchangeable; the layers above do not know which one is active.
- The whole suite runs without a phone, which is what makes 100% line and branch coverage
  practical.
- A failing day's dump, saved under `raw/debug/`, reproduces the problem offline.

### Negative / trade-offs

- Each decision costs a full dump (and stable-screen waits compare consecutive dumps), slower than
  querying one node on the device.
- Tests prove behavior on the XML only: how the real app reacts to a tap (timing, lazy-loaded
  entries) still needs a run on a phone.

### Follow-ups

- `.agents/rules/scraper-guardrails.md` cites this ADR for the layer boundaries.
- `docs/ARCHITECTURE.md` (*Layered design*) lists the modules and their dependency direction.
