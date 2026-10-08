# 0011. Non-Python linter versions follow the MegaLinter image

**Status:** Accepted · **Date:** 2026-10-08

## Context

With MegaLinter in CI ([ADR-0009](0009-quality-gates-pre-commit-locally-megalinter-in-ci.md)),
most linters run twice: in the local hooks and inside the MegaLinter image. Nothing ties the two
together by itself. When the repository has no config file by the name a MegaLinter linter looks
for, MegaLinter uses its own default (a `.pylintrc`, a `.ruff.toml` with line length 88...), and
its Flake8 does not read `pyproject.toml`. The owner's coverage-badges repository met both gaps
and settled them as below.

## Options

- **Let each side keep its versions and settings:** no work, and findings that appear on one side
  only.
- **Pin every local linter to the image's version:** the same results everywhere, but the Python
  development dependencies become `==` pins that move only with MegaLinter.
- **Pin to the image only what needs a pin anyway:** a pre-commit hook outside uv must name a
  version, so it names the image's. The Python linters stay ordinary development dependencies.

## Decision

The settings are shared everywhere; the versions are shared for the non-Python linters.

- [`.mega-linter.yml`](../../.mega-linter.yml) points the Python linters at `pyproject.toml`, and
  the settings MegaLinter would take from its defaults live in the repository (`.flake8`,
  `.markdownlint.json`, `.yamllint.yml`, `.cspell.json`, `.secretlintrc.json`, `.jscpd.json`), so
  both sides read the same files.
- The Python linters are development dependencies like any other: unpinned in `pyproject.toml`,
  locked in `uv.lock`, updated by Dependabot, run by their hooks with `uv run --locked`.
- Every other linter in the image that checks files offline is a local hook at the image's
  version: markdownlint, markdown-table-formatter, prettier, jsonlint, cspell, secretlint and jscpd
  (Node.js, in `additional_dependencies`), and betterleaks, actionlint and zizmor (their `rev`).
  pre-commit installs the Node.js and Go runtimes when they are missing.
- The pull request that bumps MegaLinter updates the hook versions by hand, from the image's
  Dockerfile; nothing checks the alignment automatically.
- The scanners that need the network or a vulnerability database (Trivy, Grype, OSV-Scanner,
  trufflehog, checkov, lychee, v8r) run only in CI.

## Consequences

### Positive

- A Markdown, YAML, JSON, spelling, secret or workflow finding shows up on commit, the same way CI
  reports it.
- The Python development dependencies update on their own schedule.

### Negative / trade-offs

- A Python linter can disagree between the hooks and CI while their versions differ.
- A MegaLinter bump that forgets the hooks lets them drift silently until a linter disagrees.
- A scanner finding shows up only in CI.

### Follow-ups

- [`docs/CI.md`](../CI.md) describes how to bump MegaLinter.
