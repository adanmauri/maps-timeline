# 0012. Pull requests check what they change; main checks everything

**Status:** Accepted · **Date:** 2026-10-08

## Context

Every pull request ran every workflow over the whole repository, whatever it touched: a docs-only
change waited for the tests, and once MegaLinter lints the whole repository
([ADR-0009](0009-quality-gates-pre-commit-locally-megalinter-in-ci.md)), a finding in a file the
pull request did not change would block it. The owner's other repositories check what changed on
pull requests and everything on `main`.

## Options

- **Everything on every pull request:** simplest, and the noise above.
- **Only what changed, everywhere:** fastest, but nothing ever looks at the whole repository, so
  findings that span files are never seen.
- **What changed on pull requests, everything on `main`:** focused pull requests, and a full run
  on every merge.

## Decision

What changed on pull requests; everything on push to `main`. The daily `security.yaml` scan always
scans the whole repository.

- **MegaLinter** gets `VALIDATE_ALL_CODEBASE: false` on pull requests and lints the files that
  differ from the merge base with `main` (`git diff origin/main...`); the checkout fetches the full
  history for it.
- A pull request that changes a file that decides what the linters report (`.mega-linter.yml`,
  `.pre-commit-config.yaml`, `pyproject.toml` and the other linter settings, `code-quality.yaml`)
  lints everything. Otherwise a stricter rule would pass its own pull request and fail `main`.
- MegaLinter's project-mode linters (Trivy, Grype, OSV-Scanner, betterleaks, secretlint,
  trufflehog, checkov, jscpd) always scan the whole repository; MegaLinter cannot narrow them.
- **Tests** run in full whenever they run. Pull requests that touch none of `maps_timeline/`,
  `tests/`, `pyproject.toml`, `uv.lock`, `.python-version` or `tests.yaml` skip them; `main` always
  runs them. `test` is a required check, so the decision is a job (`changes`) the tests depend on,
  not a `paths:` filter: a job skipped by its condition reports success, while a workflow that
  never starts leaves the check pending and blocks the merge.
- **Locally**, the hooks run on the staged files, and mypy, Pyright, Pylint and Bandit check the
  whole project whenever a Python file changes.

## Consequences

### Positive

- A pull request shows findings in the files it touches, and docs-only pull requests do not wait
  for the tests.

### Negative / trade-offs

- A pull request can pass and `main` fail, on a check that spans files or on a file the pull
  request did not touch. The fix goes in the next pull request.
- Every pull request starts the tests workflow, if only to decide to skip the tests.

### Follow-ups

- The scope logic lives in [`code-quality.yaml`](../../.github/workflows/code-quality.yaml) and
  [`tests.yaml`](../../.github/workflows/tests.yaml).
