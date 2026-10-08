# 0008. uv is the development toolchain

**Status:** Accepted · **Date:** 2026-10-08

## Context

The project was already managed with uv: `pyproject.toml` and a committed `uv.lock`, a
`.python-version` of 3.13, and `make` targets that called `uv run`. Every development tool sat in
one `dev` group, so every CI job installed all of them, the tests on the oldest supported Python
were never run apart from the development one (both were 3.13), and Dependabot watched the `pip`
ecosystem, which does not read `uv.lock`. The owner's other repositories split the groups, develop
on the newest Python and test on the oldest supported one as well.

## Options

- **Keep one `dev` group on 3.13:** no change, and the gaps above.
- **pip and `requirements*.txt`:** universal, but no lock per platform and no interpreter
  management.
- **uv with `test` and `lint` groups, two Pythons:** one tool for interpreters, environments,
  locking and running, as in the owner's other repositories.

## Decision

uv for everything in development:

- `pyproject.toml` declares the runtime dependencies with minimum versions, and the development
  tools, unpinned, in the `test` and `lint` groups; `dev` includes both and is uv's default group.
- `uv.lock` and `.python-version` (3.14) are committed. `requires-python` stays `>=3.13`, and
  `make test-compat` runs the tests on 3.13 in an isolated environment
  (`uv run --isolated --python 3.13`), so the project `.venv` stays on 3.14.
- `make` targets, the local pre-commit hooks and CI (`astral-sh/setup-uv`, `uv sync --locked`)
  call uv. A CI job installs only the group it needs.
- Dependabot watches the `uv` ecosystem, monthly, for releases at least 14 days old.

Users do not need uv to run the tool: `pipx` and `pip` install it too (see the README).

## Consequences

### Positive

- One command sets everything up (`make setup`), and the same lock drives local runs and CI.
- The `uv-lock` hook rejects a `pyproject.toml` change without its lock.
- A dependency that breaks on the oldest or the newest supported Python shows up in `make check`.

### Negative / trade-offs

- Contributors need uv installed.
- MegaLinter does not use this environment: it brings its own linters, whose versions can differ
  ([ADR-0011](0011-non-python-linter-versions-follow-the-megalinter-image.md)), and its
  pre-commands install the locked dependencies where the type checkers need them.

### Follow-ups

- [`coding-standards.md`](../../.agents/rules/coding-standards.md) cites this ADR for dependencies.
