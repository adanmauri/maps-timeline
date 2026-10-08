# maps-timeline: agent operating guidelines

Canonical, vendor-neutral instructions for AI agents working in this repo
([agents.md](https://agents.md/) standard). `CLAUDE.md` and `.github/copilot-instructions.md` are
thin pointers here.

## What this repo is

A Python CLI that recovers the Google Maps **Timeline** from an Android phone. Google keeps the
Timeline on the device only, so the tool reads what the app draws: it asks the phone for the
accessibility tree over ADB, saves each day as raw text, and turns that into a clean dataset. The
phone's official Timeline export (coordinates and place IDs, no names) merges with the scrape and
can plan which days to capture.

Two facts shape every change. The data is a person's **location history**, and the repository is
public: nothing real ever goes into it. And what the app shows can only be checked on a real
phone: a change to selectors, navigation or the walk is verified there (see
[Verification](#verification)).

## Read before working

| Concern                                                       | Source                                                                       |
|---------------------------------------------------------------|------------------------------------------------------------------------------|
| What the tool does, install, workflows, troubleshooting       | [`README.md`](README.md)                                                     |
| Every command and option                                      | [`docs/CLI.md`](docs/CLI.md)                                                 |
| Raw JSONL, official export and clean dataset schemas          | [`docs/DATA.md`](docs/DATA.md)                                               |
| How it works inside: layers, the walk, UI findings, the merge | [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)                               |
| Setup, commands, conventions, tests, dependencies, releasing  | [`docs/DEVELOPMENT.md`](docs/DEVELOPMENT.md)                                 |
| Which check runs where, CI workflows, linter versions         | [`docs/CI.md`](docs/CI.md)                                                   |
| Decisions and their rationale                                 | [`docs/adr/`](docs/adr/README.md)                                            |
| Hard constraints: location data, the phone, layers            | [`.agents/rules/scraper-guardrails.md`](.agents/rules/scraper-guardrails.md) |
| Code style and tooling                                        | [`.agents/rules/coding-standards.md`](.agents/rules/coding-standards.md)     |
| Pending work                                                  | [`TODO.md`](TODO.md)                                                         |
| How agent assets are organized                                | [`.agents/README.md`](.agents/README.md)                                     |

## Layout

```text
maps_timeline/cli.py         typer commands: run, scrape, normalize, import, stats, parse-file, dump
maps_timeline/device.py      transport: the Driver protocol, uiautomator2 and raw adb drivers
maps_timeline/navigator.py   reads the header date, taps "Día anterior"
maps_timeline/scroll.py      swipe lanes from segment bounds
maps_timeline/waits.py       stable-screen waits, the full-day dump
maps_timeline/parser.py      pure: XML dump -> DayTimeline
maps_timeline/pipeline.py    the day-by-day walk (capture or step over), raw JSONL
maps_timeline/paths.py       data/runs/<stamp>/ folders and the data/latest marker
maps_timeline/normalize.py   raw JSONL -> CSV + Parquet
maps_timeline/official.py    pure: official on-device export -> OfficialSegment
maps_timeline/history.py     every run's raw JSONL as one scrape history
maps_timeline/merge.py       aligns scrape and export, propagates names, builds the dataset
maps_timeline/planner.py     pure: which days to capture, from the export
maps_timeline/geocode.py     optional Nominatim geocoding, cached
maps_timeline/stats.py       console summary
maps_timeline/models.py      pydantic models and enums
tests/                       one file per module; synthetic fixtures in conftest.py
tooling/                     repo scripts (agent pointers, docs check, commit-msg hook), not shipped
data/                        git-ignored: runs, caches, drafts. Real location data, never committed
```

## Workflow

0. **Once per clone:** `make setup` creates the environment and installs the git hooks
   (pre-commit and commit-msg). Needs `uv`.
1. **Branch** from an up-to-date `main` with `create-branch`: `feat/...`, `fix/...`, `docs/...`,
   `chore/...`.
2. **Commit** with the `create-commit` skill (Conventional Commits, no tool attribution).
3. **Open the PR** with `write-pr` (body) and `make-pr` (mechanics).
4. **Record decisions:** a change that reverses or extends an ADR comes with a new one, from
   [`docs/adr/template.md`](docs/adr/template.md); rules cite the ADR instead of repeating it.

## Before you finish

- `make check` passes: every hook in [`.pre-commit-config.yaml`](.pre-commit-config.yaml) over the
  whole repo, then the tests on Python 3.14 with 100% line and branch coverage, and on 3.13 (the
  oldest Python the tool supports).
- `uv run maps-timeline --help` works, and so does `--help` on any command you changed.
- A parser change adds a case to `tests/test_parser.py` with a synthetic dump; a change to the
  walk, the planner or the merge adds cases to its own test file.
- README, `docs/` and this file agree with the change: options in `docs/CLI.md`, files and columns
  in `docs/DATA.md`, layers and the walk in `docs/ARCHITECTURE.md`.
- CI also runs the scanners that have no local hook (vulnerabilities, verified secrets, links,
  JSON schemas) through MegaLinter (`.github/workflows/code-quality.yaml`); check its result on
  the pull request.

## Verification

Unit tests cover parsing, planning, merging and the walk against a fake driver. They cannot prove
the app behaves the way the fakes assume. When a change touches selectors, navigation, waits,
scrolling or the walk:

1. Ask the user to connect the phone (USB debugging on) and open Google Maps on **Rutas → Día**.
   Agents never start a scrape on their own.
2. Run a short walk, such as `uv run maps-timeline scrape --days 3`, and read the counts it prints
   and the files under `raw/debug/`, not the place names.
3. Ask the user to compare the captured days with what the app shows. An agent cannot see the
   phone; do not report device behavior as verified without them.
4. Everything that run produced is real location data: it stays under `data/`, and never goes
   into a commit, a pull request or an issue.

## Boundaries

- Never push to `main`, force-push, or rewrite shared history unless the user asks for it.
- Never create tags or releases without explicit approval: a person publishes them (see
  [Releasing](docs/DEVELOPMENT.md#releasing)).
- Never commit, paste or upload real location data (see the
  [guardrails](.agents/rules/scraper-guardrails.md)).
- Never run destructive adb commands, or install or uninstall apps on the phone.
- Never add a runtime dependency without approval.
- Never bypass the hooks (`--no-verify`) or weaken a check to make it pass.
- Never attribute work to an AI tool in commits, PRs, docs or comments (see `create-commit`).
- Edit agent assets only under `.agents/`, then run `make sync-agents`; never edit the generated
  pointers in `.claude/skills/`, `.github/skills/`, `.github/instructions/` or `.cursor/rules/`.

## Skills

| Skill           | Use it to                                                 |
|-----------------|-----------------------------------------------------------|
| `create-branch` | Create a branch from an issue or a short description      |
| `create-commit` | Commit a scoped change with a Conventional Commit message |
| `write-pr`      | Fill the PR template into `pr-body.tmp`                   |
| `make-pr`       | Push and open the PR against `main`                       |
| `write-issue`   | File an issue, with the device details a scrape bug needs |
