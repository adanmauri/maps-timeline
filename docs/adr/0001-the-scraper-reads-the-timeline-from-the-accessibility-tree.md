# 0001. The scraper reads the Timeline from the accessibility tree

**Status:** Accepted · **Date:** 2026-10-08

## Context

Google moved the Timeline to on-device storage: the history lives on the phone, and Google
Takeout no longer includes it. Android can still export it (*Settings → Location → Location
services → Timeline → Export Timeline data*), but that file has coordinates and Google place IDs,
not place names or addresses. The Google Maps app shows the names, addresses and transport labels,
one day at a time, on its Routes screen.

Android exposes the UI of any app as an XML tree, the accessibility hierarchy, with the same text a
screen reader announces. On the Timeline's Day view:

- The list is a WebView. Each entry is an `android.widget.Button` whose text is in `content-desc`.
- Entries outside the viewport are still in the tree, with empty bounds, and node order is
  chronological, so most of a day reads from a single dump.
- The date header is in English ("Today", "Yesterday", "Sat Jun 6, 2026") while the entries and
  the previous-day button ("Día anterior") are in Spanish on the device the tool was built on.
- The map is a `SurfaceView` with no readable nodes.

## Options

- **Google Takeout:** the previous source of the history, which no longer includes the Timeline.
- **The official on-device export alone:** the whole history with coordinates and place IDs, but
  no names. Naming the places would take a Google API call per place ID, with a key, which the
  project does not use.
- **Screenshots and OCR:** works on any screen, but the text has to be recognized from pixels and
  the layout inferred, with a recognition engine added to the toolchain.
- **The accessibility XML over ADB:** structured text per entry, no recognition step, and the
  same channel can tap buttons. It depends on the app's labels and layout, which an app update can
  change.

## Decision

- The scraper drives the phone over ADB and reads the accessibility hierarchy (`uiautomator dump`)
  of Google Maps on the Routes screen, Day view. It reads each entry from `content-desc`, taps
  "Día anterior" and repeats, going back one day at a time.
- Selectors and regexes match the app as it renders: Spanish entry strings ("En automóvil",
  "¿Visitaste …?", "Visita desconocida", "Modo de viaje faltante"), the Spanish previous-day
  button, and the English date header. They stay untranslated in the code; everything else is in
  English.
- No Google API and no account credentials are involved: the tool reads the app the user already
  has, on a phone the user controls.
- The official export is not replaced. When present it is merged with the scrape
  ([ADR-0005](0005-the-official-export-is-merged-by-time-overlap-and-place-id.md)) and chooses which
  days to capture ([ADR-0006](0006-the-official-export-plans-the-walk-and-every-run-counts.md)).

## Consequences

### Positive

- Names, addresses, transport labels and confirmation prompts, which no other available source
  has.
- Nothing to sign up for and nothing sent to a third party.

### Negative / trade-offs

- One day per screen: a long history means a long walk, with the phone connected over USB
  debugging and Maps open on the Day view.
- An app update that renames a label or changes the layout breaks the selectors until they are
  updated from a new dump.
- The selectors assume the language mix above; another UI language needs its own strings.
- Scraping alone gives no coordinates: they come from the official export or from optional
  geocoding of the scraped addresses.

### Follow-ups

- [ADR-0003](0003-parsing-works-on-the-xml-never-on-the-device.md) keeps the logic on the XML.
- `docs/ARCHITECTURE.md` (*Why scraping the UI works*) describes the UI findings in detail.
