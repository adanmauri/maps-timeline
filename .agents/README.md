# Project agent skills

**Source of truth** for project skills lives here (`.agents/skills/`).

| Skill | Purpose |
| --- | --- |
| [`create-branch`](skills/create-branch/SKILL.md) | Branch naming and creation from a GitHub issue |
| [`make-pr`](skills/make-pr/SKILL.md) | Quality gate + `gh pr create` |
| [`write-pr`](skills/write-pr/SKILL.md) | PR description from [template](skills/write-pr/template) |
| [`write-issue`](skills/write-issue/SKILL.md) | Create GitHub issues from [template](skills/write-issue/template) |

Other locations are **stubs only** — they point here:

- [`.cursor/skills/`](../.cursor/skills/) — Cursor IDE
- Draft outputs go to `data/drafts/` (gitignored with `data/`).
- Do not duplicate skill bodies outside `.agents/skills/`.
