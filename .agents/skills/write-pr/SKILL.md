---
name: write-pr
description: Draft a Pull Request description for maps-timeline using the project template ($ARGUMENTS optional GitHub issue).
---

# Write Pull Request Description

Draft a PR description for **maps-timeline** using the
[template](./template). Optional $ARGUMENTS: GitHub issue number for context and
linking.

## When to use

Before `gh pr create` or when the user asks for a PR write-up.

## Steps

1. Read the branch diff: `git diff main...HEAD` and recent commits.
2. If $ARGUMENTS is a GitHub issue, fetch title and description (GitHub MCP or
   `gh issue view`).
3. Fill every section of the [template](./template):
   - **Summary** — what changed and why (user-visible impact).
   - **Type of change** — check applicable boxes.
   - **Testing** — exact commands run (`make quality`, `make test`, `parse-file`
     on which dump). Mention offline vs device testing.
   - **Checklist** — mark completed items honestly.
4. Save to `data/drafts/PR.md` (`data/` is gitignored; do not commit unless the
   user asks).

## maps-timeline specifics

| Layer touched | Mention in Testing |
| --- | --- |
| `parser.py` | `parse-file` on relevant dump; `summary_matches()` |
| `pipeline.py` / `navigator.py` | unit tests; note if live device test was done |
| `normalize.py` | re-run `normalize` on sample JSONL |
| `cli.py` | `uv run maps-timeline --help` and affected subcommand |
| Docs only | link updated files |

Reference issues: `Fixes #N` or `Relates to #N`.

## Best practices

- Be concise; lead with the **why**.
- Call out **breaking changes** to JSONL schema or CLI flags explicitly.
- Do not paste real addresses or coordinates from Timeline data.
