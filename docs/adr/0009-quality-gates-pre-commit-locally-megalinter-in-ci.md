# 0009. Quality gates: pre-commit locally, MegaLinter in CI

**Status:** Accepted · **Date:** 2026-10-08

## Context

The Python checks ran in three places with three lists. `make quality` ran Ruff, Flake8, Pylint,
mypy, Pyright, Bandit and Trivy (when installed) and `make test` the tests. The pre-commit hooks
formatted on commit and ran both targets on push. CI ran `make lint` and `make type-check`, the
tests, and Bandit with Trivy. Markdown, YAML, JSON, the workflows, spelling and secrets had no
checker, and an agent had two commands to remember for "done". The owner's other repositories run
one `.pre-commit-config.yaml` from the commit hook and `make check`, and MegaLinter in CI.

## Options

- **Keep the `make` targets:** they work for Python, and nothing checks the rest of the repository.
- **pre-commit everywhere, no MegaLinter:** one list and fast feedback, but no scanner that needs
  the network or a vulnerability database (dependency vulnerabilities, links, JSON schemas).
- **pre-commit locally, MegaLinter in CI:** fast local feedback on everything that can run
  offline, and the broad sweep in CI; the Python linters appear in both.

## Decision

- **Locally:** [`.pre-commit-config.yaml`](../../.pre-commit-config.yaml) is the list. The commit
  hook runs it on staged files; `make lint` runs it on the whole repository; `make check` adds the
  tests on Python 3.14 (with coverage) and 3.13. It covers file hygiene, secrets, the `uv-lock`
  check, the Python linters (through `uv run`), workflows, Markdown, YAML, JSON, spelling and
  copied code ([ADR-0011](0011-non-python-linter-versions-follow-the-megalinter-image.md) lists
  them), agent pointer sync, docs links and the ADR index, and the commit-msg check against tool
  attribution.
- **In CI:** MegaLinter's Python flavor, configured in [`.mega-linter.yml`](../../.mega-linter.yml),
  plus the tests (`tests.yaml`) and the daily security scan (`security.yaml`). Every active linter
  blocks, formatters included.
- Every linter MegaLinter runs on files offline is also a local hook, with the same settings, so a
  commit that passes locally does not fail there unless a Python linter's version differs.

[`docs/CI.md`](../CI.md) keeps the map of which tool runs where.

## Consequences

### Positive

- `make check` is the definition of done, for people and agents alike.
- The commit hook catches most problems before a push.

### Negative / trade-offs

- Two lists to keep aligned: a Python linter added to one goes into the other.
- The first `make setup` downloads the Node.js and Go runtimes some hooks need.

### Follow-ups

- [ADR-0011](0011-non-python-linter-versions-follow-the-megalinter-image.md) ties the versions of
  the two lists together; [ADR-0012](0012-pull-requests-check-what-they-change-main-checks-everything.md)
  sets what each pull request checks.
