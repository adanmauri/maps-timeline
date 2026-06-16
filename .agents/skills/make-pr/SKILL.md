---
name: make-pr
description: Create a GitHub Pull Request for maps-timeline after quality checks ($ARGUMENTS optional issue link).
---

# Make Pull Request

Create a PR for **maps-timeline** using the GitHub CLI (`gh`). Optional $ARGUMENTS:
GitHub issue number or PR title hint.

## When to use

Code changes are complete and ready for review. **Cancel PR creation** if any gate
step fails.

## Steps

1. **Run the quality gate** (requires `uv sync` / `.venv`):

   ```bash
   make quality    # lint + type-check + security (bandit)
   make test       # pytest, 100% coverage on maps_timeline/
   ```

   Parser changes — also verify offline:

   ```bash
   uv run maps-timeline parse-file dump_dia.xml
   ```

2. **Update branch with `main`**

   ```bash
   git fetch origin main
   git rebase origin/main
   # resolve conflicts if any
   git push --force-with-lease
   ```

3. **Branch name** — must match conventions (see `create-branch` skill):
   `feat/…`, `fix/…`, `docs/…`, `chore/…`.

4. **Draft description** — invoke the `write-pr` skill (or read
   [`.agents/skills/write-pr/template`](../write-pr/template)). Save draft to
   `data/drafts/PR.md` if useful.

5. **Create the PR**

   ```bash
   mkdir -p data/drafts
   gh pr create --title "<title>" --body-file data/drafts/PR.md
   ```

   Title examples:
   - `fix(parser): handle missing transit mode`
   - `feat(cli): add --jsonl flag to stats`
   - `docs: expand troubleshooting section`

   Link issues: `Fixes #42` in the body when applicable.

## Best practices

- **Conventional Commits** on branch commits:
  - `feat: add scroll reset after day change`
  - `fix: parse European distance decimals`
  - `docs: document data/runs layout`
  - `test: cover timeline_panel_collapsed`
- Never commit `data/`, real XML dumps, or screenshots with locations.
- Pre-commit hooks: `make install-dev` sets them up; they run on commit.
- See [`docs/DEVELOPMENT.md`](../../../docs/DEVELOPMENT.md) for the full checklist.
