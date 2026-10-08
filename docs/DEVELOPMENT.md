# Development

How to set up, check and change this repository. What the tool does for its users is in the
[README](../README.md) and [CLI.md](CLI.md), the files it writes in [DATA.md](DATA.md), how it
works inside in [ARCHITECTURE.md](ARCHITECTURE.md), and what checks a change, locally and in CI,
in [CI.md](CI.md).

## Setup

Needs [uv](https://docs.astral.sh/uv/) and `git`; `adb` only to run against a phone. uv installs
the Python versions it needs, and pre-commit installs the Node.js and Go runtimes some hooks need
when they are missing (the first `make setup` takes a few minutes for that).

```bash
make setup   # uv sync --locked, then installs the pre-commit and commit-msg hooks
make check   # everything that must pass before a change is done
```

`make setup` creates `.venv` with the Python in `.python-version` (3.14) and the `dev` dependency
group. Editors pick it up from `.venv/bin/python` (VS Code is preconfigured).

## Commands

| Command             | What it does                                                                                    |
|---------------------|-------------------------------------------------------------------------------------------------|
| `make check`        | `lint`, then `test` and `test-compat`: the definition of done                                   |
| `make lint`         | Every hook in [`.pre-commit-config.yaml`](../.pre-commit-config.yaml) over the whole repository |
| `make test`         | pytest with 100% line and branch coverage on `maps_timeline/`, on the development Python        |
| `make test-compat`  | The tests on Python 3.13, the oldest the tool supports, in a throwaway environment              |
| `make clean`        | Remove caches and coverage reports (keeps `.venv` and `data/`)                                  |
| `make sync-agents`  | Regenerate the agent pointers from `.agents/`                                                   |
| `make check-agents` | Fail if the agent pointers drifted                                                              |
| `make help`         | List the targets, including the CLI shortcuts ([CLI.md](CLI.md#makefile-shortcuts))             |

Pass pytest options straight to uv: `uv run pytest tests/test_parser.py -k unconfirmed`.

## Conventions

The binding checklists are [`.agents/rules/coding-standards.md`](../.agents/rules/coding-standards.md)
and [`.agents/rules/scraper-guardrails.md`](../.agents/rules/scraper-guardrails.md), for people and
agents alike. The short version:

- **Language:** code, comments, docs, commit messages and CLI messages in English. The Spanish
  strings the Google Maps app renders (`"Día anterior"`, `"En automóvil"`) are selectors, never
  translated.
- **Python:** 3.13+ syntax; built-in generics and `X | None`; type hints everywhere; a docstring on
  every module, class and function; Pydantic for the models.
- **Layers:** interpretation works on the XML in pure functions; the drivers stay dumb; `cli.py`
  stays thin.
- **Data:** nothing real in the repository. Fixtures are synthetic, and a real dump is anonymized
  before it leaves your machine.
- **Commits:** [Conventional Commits](https://www.conventionalcommits.org/)
  (`fix(parser): ...`, `feat(cli): ...`), one concern per commit, no tool attribution.
- **Branches:** `feat/...`, `fix/...`, `docs/...`, `chore/...` from an up-to-date `main`; never
  push to `main`.
- **Pull requests:** fill [the template](../.github/PULL_REQUEST_TEMPLATE.md); the test plan lists
  only what was actually run.

## Testing

- **No phone, network or real clock.** Drivers, `subprocess` and HTTP are faked, and the CLI tests
  pin today's date. Parser, official export, planner and stats are pure functions.
- **100% line and branch coverage** on `maps_timeline/` (`--cov-fail-under=100` in
  `pyproject.toml`): every new path needs a test.
- **Fixtures** (`tests/conftest.py`):
  - `FakeDriver` and `MinimalDriver`: record taps and swipes, return canned XML.
  - `day_dump_xml()`, `button_xml()`, `text_xml()`: synthetic Timeline dumps.
  - `sample_jsonl` and `official_export_payload()` / `sample_export`: a scraped sample and an
    official export sample that describe the same days, so the merge has something to match.
  - `isolated_paths` and `isolated_place_names_cache`, both autouse: every test gets its own
    `data/runs/`, `data/latest` and `data/cache/places.json` under `tmp_path`.
  - `write_run_scrape()` and `scraped_visit_day()`: raw JSONL inside a versioned run folder, for
    the scrape history and the planner.
- **What tests cannot show:** how the app behaves on a real phone. A change to selectors,
  navigation, waits or the walk is checked with a short live run, as
  [`AGENTS.md`](../AGENTS.md#verification) describes.

### Offline parser workflow

1. Capture: `uv run maps-timeline dump --out my_screen.xml`, or take a dump from `raw/debug/`
   after a failed scrape.
2. **Anonymize** place names and addresses before anything leaves your machine.
3. Parse: `uv run maps-timeline parse-file my_screen.xml`, and check the segment count matches the
   day's summary (`summary_matches()`).
4. Add a test to `tests/test_parser.py` with a synthetic dump built from the fixtures.

## Common changes

### A new segment type or UI string

1. Extend `SegmentType` and the classification in `parser.py`.
2. Add tests with synthetic `content-desc` strings.
3. Confirm `normalize.py` passes the type through unchanged.
4. Update the segment table in [`DATA.md`](DATA.md).

### A new CLI option

1. Add it in `cli.py` as `Annotated[..., typer.Option(...)]`, or reuse a shared alias (`_Serial`,
   `_Since`...).
2. Delegate to the module that owns the logic.
3. Test it through `tests/test_cli.py` (Typer's `CliRunner`), and document it in
   [`CLI.md`](CLI.md).

### A parser bug from a real phone

1. Reproduce it with an anonymized dump and `parse-file`.
2. Fix `parser.py` and add a regression test with a synthetic dump.
3. Run `normalize` again on the existing runs: no new scrape is needed.

### A raw JSONL change

Avoid it. Every run ever captured must still normalize: keep `models.py` compatible with the JSONL
already written, or document the break in [`DATA.md`](DATA.md) and mark the pull request breaking.

## Dependencies

uv manages the interpreters, the environment, the lock and every command; never `pip`.

- Runtime dependencies are in `[project.dependencies]`, sorted, with minimum versions. Adding one
  needs a reason in the pull request: `uv add <package>`.
- Development tools are in the `test` and `lint` groups, unpinned there and pinned in `uv.lock`,
  which is committed: `uv add --group <test|lint> <package>`. `make setup` installs both groups
  (`dev`); CI installs only the group a job needs, with `--locked`.
- `.python-version` (3.14) is the development Python; the 3.13 tests run in a throwaway
  environment, so `.venv` stays on 3.14.
- Dependabot opens monthly updates for `uv.lock` and the actions, for releases at least 14 days
  old. Pick the same age when bumping anything by hand.
- The pre-commit hooks outside uv pin the MegaLinter image's versions; how to bump them is in
  [CI.md](CI.md#same-settings-and-mostly-the-same-versions).

## Agent assets

AI agents follow [`AGENTS.md`](../AGENTS.md), the one canonical instructions file; `CLAUDE.md` and
`.github/copilot-instructions.md` only point to it. Rules (`.agents/rules/`) and skills
(`.agents/skills/`) live once, in [`.agents/`](../.agents/README.md), and `tooling/sync_agents.py`
writes a thin pointer for each tool in `.claude/skills/`, `.github/skills/`,
`.github/instructions/` and `.cursor/rules/`. Pointers are generated and committed: edit the file
in `.agents/`, then run `make sync-agents`; `make check` fails when they drift. Skills write their
drafts to git-ignored `*.tmp` files. No tool is credited in commits, pull requests or docs, and a
commit-msg hook rejects attribution lines.

## Releasing

Releases are made by a person: agents prepare the notes and the commands, and
`.claude/settings.json` does not let them create tags or releases. With immutable releases turned
on, a published `vX.Y.Z` tag and its files can never move or be deleted, so a release is final.

1. Merge everything for the release to `main`, bumping `version` in `pyproject.toml` the same way,
   and wait for the workflows on `main` to pass.
2. Write the notes: what changes for users, requirements, known limits, breaking changes, and the
   changelog.
3. Run the **Release** workflow from the Actions tab on `main` with the tag (`vX.Y.Z`, matching
   `version`). It builds the wheel and the sdist and creates a draft release pinned to that commit,
   with generated notes. A draft creates its tag only when published.
4. Replace the draft's notes with the ones from step 2, check the files, and publish it from the
   web.

A release that breaks the raw JSONL, a command or option, or the dataset columns is a new major
version (a new minor one while the version is `0.x`).
