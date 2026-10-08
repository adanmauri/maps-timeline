---
name: make-pr
description: Create pull requests with consistent title/body, correct base branch, and verified branch state. Use when the user asks to open a PR from the current branch.
---

# Make Pull Request

## Objective

Open a pull request from the current branch: validate state, push, and create
the PR. The body content is produced by the `write-pr` skill: this skill owns
the **mechanics**, not the prose.

## Workflow

1. Validate repository state:
   - `git status --short --branch`
   - Confirm current branch is not `main` and follows `feat/`, `fix/`, `docs/` or `chore/`.
2. Confirm the gate passed on the final state of the branch: `make check` (see `AGENTS.md`,
   Before you finish). If it fails, stop and fix it; never open the PR around a failing check.
3. Understand PR scope:
   - `git log --oneline origin/main...HEAD`
   - `git diff --stat origin/main...HEAD`
   - Nothing under `data/`, no official export, dump or screenshot in the diff.
4. Ensure remote branch exists:
   - If needed: `git push -u origin HEAD`
5. Draft PR title:
   - Format: `<type>(<scope>): <short outcome>`, e.g. `fix(parser): read unconfirmed visits`
   - `!` after the scope when it breaks the raw JSONL, the CLI or the dataset columns.
   - Reuse commit intent when possible.
6. Get the PR body from the **`write-pr`** skill (it fills the repo template into
   `pr-body.tmp`). If `write-pr` has not been run, run it first, do not draft
   the body here.
7. Create PR:
   - `gh pr create --base main --head <branch> --title "<title>" --body-file pr-body.tmp`
   - Or a GitHub MCP server if one is connected.
8. Report outcome:
   - PR URL
   - base/head branches
   - final title used

## Safety Rules

- Never open PR from `main`.
- Never force push unless explicitly requested.
- Do not change git config.
- If `gh` (or a GitHub MCP) is not authenticated, stop and ask the user to authenticate.
- No tool attribution in the title or body (see `create-commit`).

## Body

The PR body comes from the `write-pr` skill, which fills the repo template
([`.github/PULL_REQUEST_TEMPLATE.md`](../../../.github/PULL_REQUEST_TEMPLATE.md))
into `pr-body.tmp`. `gh pr create` also applies that template automatically when
no body is passed.

## Command Template

```bash
git status --short --branch
make check
git log --oneline origin/main...HEAD
git diff --stat origin/main...HEAD
git push -u origin HEAD
gh pr create --base main --head <branch> --title "<title>" --body-file pr-body.tmp
```
