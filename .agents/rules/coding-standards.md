---
description: Coding standards for AI agents and humans working in maps-timeline
---

# Rules: coding standards

Binding checklist. The tools enforce most of it: `make check` locally, MegaLinter in CI
([ADR-0009](../../docs/adr/0009-quality-gates-pre-commit-locally-megalinter-in-ci.md)). The map of
which tool runs where is in [`docs/CI.md`](../../docs/CI.md). What the scraper may do with the
phone and the data is in the [scraper guardrails](scraper-guardrails.md).

## Python

- MUST run on **Python 3.13+** (`requires-python`). Development uses the Python in
  `.python-version` (3.14), and `make check` also runs the tests on 3.13.
- `from __future__ import annotations` in every module.
- Built-in generics and unions: `dict[str, int]`, `list[str] | None`. Import from `typing` or
  `collections.abc` only what has no built-in form (`Any`, `Protocol`, `Callable`, `cast`,
  `Literal`, `TYPE_CHECKING`); never `Optional`, `Dict`, `List`, `Tuple`, `Set` or `Union`.
- Type hints on every function and method signature; Pydantic for the domain models
  (`models.py`).
- Black and isort (Black profile), line length 100; Ruff, Flake8, Pylint, mypy and Pyright clean.
- A docstring on every module, class and function, private helpers and tests included: one line by
  default, several only past about 100 characters or to list structured information. No `Args:` or
  `Returns:` sections, and no blank line between the docstring and the code.
- Relative imports inside `maps_timeline`, grouped standard library, third-party, local. Heavy or
  device-only imports (`uiautomator2`) may be deferred into the function that needs them.
- Private helpers carry the `_` prefix.
- Specific exceptions: `ValueError` for invalid input, `FileNotFoundError` for missing files,
  `RuntimeError` for device connection failures. The message says what is wrong and what to do.
- Code, comments, docstrings and CLI messages in English. The only Spanish strings are the UI
  selectors that must match the Google Maps app (see the [guardrails](scraper-guardrails.md)).
- CLI messages read well without their markers (`[✓]`, `[!]`, `[·]`); no other emojis.

## Suppressions

- Fix the code first: refactor, tighten a type or restructure before silencing a checker.
- No global ignores, except ecosystem-wide conflicts: Flake8 `E203` and `W503` and Ruff `E501`
  (Black owns wrapping), and mypy `ignore_missing_imports` for modules without stubs
  (`uiautomator2`, `pyarrow`).
- Inline suppressions go on the offending line, with the reason when it is not obvious:
  - `# pylint: disable=import-outside-toplevel` on deferred imports (startup cost);
  - `# nosec B603` on fixed-argv `subprocess.run(...)` calls in `device.py`;
  - `# nosec B405` / `# nosec B314` on `xml.etree` over local adb output or saved dumps;
  - `# pylint: disable=unnecessary-ellipsis` on `...` in `typing.Protocol` bodies;
  - `# noqa` or `# type: ignore[...]` only when the checker is wrong and nothing cleaner exists.
- Typer options use `Annotated[..., typer.Option(...)]`, never `# noqa: B008`.

## Tests

- pytest under `tests/`: one file per module (`test_parser.py`, `test_planner.py`...) plus
  `conftest.py` for shared fixtures.
- `maps_timeline/` stays at **100% line and branch coverage** (`--cov-fail-under=100`).
- No test needs a phone, the network or the real clock: drivers, `subprocess`, HTTP and time are
  faked (`FakeDriver`, mocked geocoding, a pinned `today`).
- Fixtures are synthetic, and describe the same days: the scraped sample (`sample_jsonl`) and the
  official export sample (`official_export_payload()`) line up, so a merge test that stops
  matching points at a merge bug. Never a real export, a real dump or a real place name.
- Every test gets its own `data/` under `tmp_path` (the autouse `isolated_paths` and
  `isolated_place_names_cache` fixtures); no test reads or writes the repository's `data/`.

## Dependencies: [ADR-0008](../../docs/adr/0008-uv-is-the-development-toolchain.md)

- **uv** for everything: `uv sync`, `uv run`, `uv add <package>` for the runtime and
  `uv add --group <test|lint> <package>` for development. NEVER call `pip`, create a virtualenv by
  hand or edit `uv.lock`, which is committed; CI installs with `--locked`.
- Runtime dependencies are sorted alphabetically with a minimum version; a new one needs approval
  and a reason in the pull request.
- Development tools are unpinned in `pyproject.toml` and pinned in `uv.lock`.
- The non-Python hooks in `.pre-commit-config.yaml` pin the MegaLinter image's versions and move
  only with it
  ([ADR-0011](../../docs/adr/0011-non-python-linter-versions-follow-the-megalinter-image.md)).
  NEVER bump one on its own.

## Workflows: [ADR-0013](../../docs/adr/0013-actions-are-pinned-to-a-commit.md)

- Every `uses:` is pinned to a full commit SHA with the version in a comment
  (`@<sha> # v7.0.1`), and a `docker://` image to its digest (`:vX.Y.Z@sha256:...`).
- `permissions: {}` at the top of every workflow, and each job asks for what it needs.
  `persist-credentials: false` on every checkout whose job does not push.
- A tag, release or package that disappeared or moved is a signal, not housekeeping: read the
  upstream advisories and check this repository's runs before replacing it.
- What a tool's container ships (versions, venvs, uv) is read from its Dockerfile at the pinned
  commit, never assumed.
