# Development guide

Guide for contributors and maintainers of `maps-timeline`.

## Environment setup

### Prerequisites

- Python **3.13+**
- [uv](https://docs.astral.sh/uv/)
- `adb` on `PATH` (only for live device testing)

### Install

```bash
uv sync                    # production + dev dependencies, creates .venv
```

For pre-commit hooks (recommended before committing):

```bash
make install-dev           # uv sync --group dev + pre-commit install
```

Hooks are defined in `.pre-commit-config.yaml` and mirror the Make targets:

| When | Hooks | Equivalent |
| --- | --- | --- |
| **commit** | trailing whitespace, YAML/TOML checks, black, isort, ruff --fix | `make format` |
| **pre-push** | `make quality`, `make test` | ruff, flake8, pylint, mypy, pyright, bandit, pytest (100% coverage) |

Run manually: `uv run pre-commit run --all-files` (commit stage) or add
`--hook-stage pre-push` for the full gate.

### Verify

```bash
uv run maps-timeline --help
make test
```

---

## Project layout

```
maps_timeline/          # application package (one module per layer)
tests/                  # pytest, one test file per module + conftest.py
docs/                   # architecture, CLI, data, development guides
data/                   # gitignored export output (local only)
dump_*.xml              # sample XML dumps for offline parser tests
pyproject.toml          # metadata, tool config, dependencies
uv.lock                 # pinned lockfile (commit changes)
Makefile                # quality and CLI shortcuts
AGENTS.md               # AI agent guidelines (keep in sync with docs)
```

See [`ARCHITECTURE.md`](ARCHITECTURE.md) for module responsibilities.

---

## Make targets

Run `make help` for the full list.

### Environment

| Target | Description |
| --- | --- |
| `install` | `uv sync --no-group dev` (production only) |
| `install-dev` | Full sync + pre-commit hooks |
| `clean-cache` | Remove `__pycache__`, pytest/coverage caches |
| `clean-deps` | Remove `.venv` and uv cache |
| `clean` | `clean-cache` + `clean-deps` |

### CLI wrappers

| Target | Example |
| --- | --- |
| `run` | `make run ARGS="run --days 3"` |
| `scrape` | `make scrape ARGS="--days 7"` |
| `normalize` | `make normalize ARGS="--geocode"` |
| `parse-file` | `make parse-file FILE=dump_dia.xml` |
| `dump` | `make dump OUT=dump.xml` |

### Quality gate

| Target | Tools |
| --- | --- |
| `lint` | ruff, flake8, pylint |
| `type-check` | mypy, pyright |
| `security` | bandit (+ trivy if installed) |
| `test` | pytest with 100% coverage enforcement |
| `test-coverage` | pytest + HTML report in `htmlcov/` |
| `quality` | lint + type-check + security |
| `format` | black, isort, ruff --fix |
| `format-quality` | format then quality |

**Before opening a PR:**

```bash
make quality
```

Or run individual targets on a subset:

```bash
make lint maps_timeline
make type-check tests
```

---

## Testing

### Philosophy

- **No phone required** for CI or day-to-day development.
- Parser, normalize, stats, and models are **pure functions**.
- Device code uses mocked subprocess / `FakeDriver`.
- Geocoding HTTP is mocked.

### Running tests

```bash
make test                              # full suite
make test ARGS="-k parser"             # filter by name
make test-coverage                     # HTML report
uv run pytest tests/test_parser.py -v  # single file
```

### Coverage

`pyproject.toml` enforces **100% line and branch coverage** on `maps_timeline/`
(`--cov-fail-under=100`). Every new code path needs a test.

### Fixtures (`tests/conftest.py`)

- `FakeDriver` — records taps/swipes, returns canned XML.
- Synthetic XML builders for Timeline segments and headers.
- Sample JSONL strings for normalization tests.

### Offline parser workflow

1. Capture: `uv run maps-timeline dump --out my_screen.xml` (or copy from
   `raw/debug/` after a failed scrape).
2. **Anonymize** place names and addresses.
3. Test: `uv run maps-timeline parse-file my_screen.xml`
4. Assert `summary_matches()` is `True` when possible.
5. Add a unit test in `tests/test_parser.py` using inline XML or a committed
   fixture (scrubbed dumps only).

---

## Code standards

Full rules live in [`AGENTS.md`](../AGENTS.md). Summary:

| Topic | Rule |
| --- | --- |
| Language | English for code, comments, CLI messages |
| Spanish strings | Only UI selectors matching Google Maps (e.g. `"Día anterior"`) |
| Types | Python 3.13 syntax (`list`, `str \| None`, no `Optional`) |
| Models | Pydantic in `models.py` |
| Docstrings | Every module, class, and function; no `Args:`/`Returns:` sections |
| Line length | 100 (black) |
| Imports | stdlib → thirdparty → local; relative within package |
| Layers | No device imports in parser/normalize/stats |

### Adding a dependency

```bash
uv add <package>              # production
uv add --dev <package>        # development
```

Never hand-edit `uv.lock`. Keep `[project.dependencies]` alphabetically sorted.

---

## Common change patterns

### New segment type or UI string

1. Extend `SegmentType` and classification in `parser.py`.
2. Add tests with synthetic `content-desc` strings.
3. Confirm `normalize.py` passes the type through unchanged.
4. Update [`DATA.md`](DATA.md) segment table.

### New CLI option

1. Add `Annotated[..., typer.Option(...)]` in `cli.py`.
2. Delegate to the appropriate module (keep CLI thin).
3. Test via `tests/test_cli.py` (Typer `CliRunner`).

### Parser bug from real device

1. Save XML to `dump_*.xml` (anonymized).
2. `uv run maps-timeline parse-file dump_*.xml` — note `summary_matches()`.
3. Fix `parser.py`; add regression test.
4. Re-normalize existing JSONL — no re-scrape needed.

### Breaking JSONL schema change

Avoid when possible. If unavoidable:

1. Document in PR and [`DATA.md`](DATA.md).
2. Ensure `normalize.py` handles old and new shapes, or bump major version.

---

## Pre-commit

`make install-dev` registers hooks for **commit** and **pre-push**. Fix hook
failures before committing; if a hook auto-formats files, stage the result in a
**new** commit (do not amend unless you own the previous unpushed commit).

---

## Pull request checklist

- [ ] `make quality` and `make test` pass
- [ ] Offline parse tested when `parser.py` changed
- [ ] Docs updated (`README.md`, `docs/`, `AGENTS.md`) when behavior or CLI changes
- [ ] No real location data in commits (no `data/`, no unscrubbed dumps)
- [ ] Spanish UI strings left untranslated in selectors

---

## Project automation

| Path | Role |
| --- | --- |
| `.agents/skills/` | **Source of truth** — `create-branch`, `make-pr`, `write-pr`, `write-issue` |
| `.cursor/skills/` | Stubs → `.agents/skills/` |
| `.cursor/rules/` | Cursor rule → `AGENTS.md` |
| `.github/workflows/` | CI (`tests`, `quality`, `security`, `release`) |
| `data/drafts/` | Local PR/issue drafts from skills (under gitignored `data/`) |

See [`.github/README.md`](../.github/README.md).

---

## Security notes

- `bandit` scans `maps_timeline/` only (`make security`).
- `# nosec` suppressions are documented in `AGENTS.md` (trusted local XML, fixed
  argv subprocess).
- Never log addresses or coordinates in debug messages unnecessarily.
- Do not run destructive ADB commands beyond UI navigation for scraping.
