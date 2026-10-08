# TODO

## Verification

On a phone, with the user looking at it (see [`AGENTS.md`](AGENTS.md#verification)):

- The planned walk (`run --export`): stepping over unplanned days works in the app, and Ctrl+C
  keeps the days captured so far.
- How the app shows nested visits (`hierarchy_level = 1` in the export). If it does not list them,
  the planner looks for them on days that cannot name them, until `MAX_ATTEMPTS` skips them.
- The times the app shows line up with the export's local times, which the merge relies on.

## Features

- Check propagated names: flag a place ID whose learned name differs between days before spreading
  it to every visit. Decide after the first real planned run.
- Jump to a day through the Timeline's calendar instead of walking back to it, so a plan whose
  newest day is weeks back does not step over every newer day.
- Save the official export over ADB instead of asking the user to export it from the phone's
  settings.

## Releases

- No release is published yet. Decide where the first one (`v0.1.0`) goes: GitHub Releases only,
  or PyPI too (see [Releasing](docs/DEVELOPMENT.md#releasing)).
