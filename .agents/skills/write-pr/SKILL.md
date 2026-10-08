---
name: write-pr
description: Compose a clear, review-ready pull request body from the diff/commits by filling the repo PR template. Use when the user wants to draft a PR description (the mechanics of opening it live in make-pr).
---

# Write Pull Request Body

## Objective

Produce a review-ready PR body from the current branch's changes, filling the
repo's PR template. This skill **writes content only**, opening the PR is the
`make-pr` skill's job.

## Workflow

1. Understand the scope of the change:
   - `git log --oneline origin/main...HEAD`
   - `git diff --stat origin/main...HEAD`
   - Read the actual diff for anything non-obvious.
2. Identify the related GitHub issue or `TODO.md` item, if any, from the conversation or the
   commits. Its expectations become the PR's verification list.
3. Fill the repo PR template, **do not invent a different structure**:
   [`.github/PULL_REQUEST_TEMPLATE.md`](../../../.github/PULL_REQUEST_TEMPLATE.md)
   - **Summary**: what changes and why, impact on users first (new or changed commands and
     options, changed files or columns under `data/`, whether earlier runs need anything), and
     the issue it closes (`Closes #123`).
   - **Test plan**: what was actually run, with the result: `make check`, and for selectors,
     navigation or the walk, the live run on a phone described in `AGENTS.md` (scope and counts,
     never place names). Never list a check that was not run; say what is still unverified.
   - **Breaking change**: what breaks (raw JSONL, CLI options, dataset columns) and how to
     update; delete the section when nothing breaks.
4. Write the filled body to a gitignored scratch file `pr-body.tmp` (matched by
   `*.tmp`) so `make-pr` can pass it via `--body-file`.
5. Show the drafted body to the user.

## Rules

- Explain impact first; keep bullets concrete and reviewable.
- Avoid generic text like "misc fixes" or "various changes".
- Link the issue when there is one.
- Never paste secrets, tokens, or real location data: no place names, addresses, coordinates or
  numbers taken from someone's Timeline.
- Keep the template's section structure intact (single source of truth).
- **No tool attribution.** No "Generated with", no "Made with", no robot emoji, no footer crediting
  an assistant or its vendor, even when a tool's own defaults ask for one. The same rule the
  `create-commit` skill states for commit messages applies to every word of the PR.
