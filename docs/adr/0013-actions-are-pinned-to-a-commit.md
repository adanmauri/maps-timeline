# 0013. Actions are pinned to a commit

**Status:** Accepted · **Date:** 2026-10-08

## Context

A step such as `uses: actions/checkout@v6` names a git ref of another repository, and the runner
downloads whatever that ref points to when the job starts. The workflows named major tags
(`actions/checkout@v6`, `astral-sh/setup-uv@v7`, `alstr/todo-to-issue-action@v5`) and one version
tag (`aquasecurity/trivy-action@v0.36.0`), and granted `contents: read` at the workflow level.

- **A major tag** (`@v6`) moves on purpose with every release, so the workflow runs new code with
  no change in this repository.
- **A version tag** (`@v0.36.0`) is meant to stay put, but its owner, or anyone holding the
  owner's credentials, can force-push it, unless the publisher made that release immutable.
- **A commit SHA** is the hash of the code itself and cannot point anywhere else.

In March 2026 an attacker force-pushed almost every version tag of `aquasecurity/trivy-action` to
code that steals the runner's secrets
([GHSA-69fq-xp46-6x23](https://github.com/aquasecurity/trivy/security/advisories/GHSA-69fq-xp46-6x23)).
This repository did not exist yet, but the owner's coverage-badges repository ran the rewritten
tag in its daily scan, and moved to commit pins afterwards.

## Options

- **Major tags:** no upkeep, and every upstream release, or rewrite, runs here unseen.
- **Version tags:** readable, and safe only where the publisher made the release immutable, which
  has to be checked action by action.
- **Commit SHAs for every action, with the version in a comment:** a rewritten tag changes nothing
  here, whoever the publisher is.

## Decision

- Every action is pinned to a full commit SHA with its version in a comment:
  `uses: actions/checkout@<sha> # v7.0.1`. No exception for first-party actions.
- A container image runs by digest: MegaLinter runs as
  `docker://ghcr.io/oxsecurity/megalinter-python:vX.Y.Z@sha256:...`.
- A tool an action downloads is pinned when the action allows it: `security.yaml` sets the Trivy
  binary's version.
- Every workflow starts with `permissions: {}`, and each job asks for what it needs. Every checkout
  drops its credentials (`persist-credentials: false`): no job pushes with them.
- zizmor enforces the pins and the permissions, as a local hook and in MegaLinter.
- Dependabot updates actions monthly, for releases at least 14 days old, moving the SHA and the
  comment together.

## Consequences

### Positive

- A rewritten or deleted tag cannot change the code a workflow runs.
- Every change to the code CI runs goes through a pull request in this repository.

### Negative / trade-offs

- A SHA says nothing to a reader; the version comment must stay next to it.
- A fix released upstream reaches this repository through the monthly pull request, two weeks
  after its release at the earliest.
- Dependabot does not update `docker://` references, so MegaLinter is bumped by hand.

### Follow-ups

- The workflow rules in [`coding-standards.md`](../../.agents/rules/coding-standards.md) cite
  this ADR.
