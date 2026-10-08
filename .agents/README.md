# `.agents/`: agent configuration (vendor-neutral)

Single source of truth for agent skills and rules, following the
[`.agents` protocol](https://dotagentsprotocol.com/). The operating manual is the repo-root
[`AGENTS.md`](../AGENTS.md), where the [agents.md](https://agents.md/) standard discovers it;
[`CLAUDE.md`](../CLAUDE.md) and [`.github/copilot-instructions.md`](../.github/copilot-instructions.md)
are hand-authored pointers to it. Why it is organized this way:
[ADR-0010](../docs/adr/0010-agent-assets-live-in-agents-with-generated-pointers.md).

```text
.agents/skills/{id}/SKILL.md   frontmatter: name (== folder name, kebab-case) and description
.agents/rules/{stem}.md        frontmatter: description; terse, binding checklists
```

The protocol spells the file `skill.md`; `SKILL.md` keeps Claude Code compatibility.

| Skill                                            | Use it to                                                 |
|--------------------------------------------------|-----------------------------------------------------------|
| [`create-branch`](skills/create-branch/SKILL.md) | Create a branch from an issue or a short description      |
| [`create-commit`](skills/create-commit/SKILL.md) | Commit a scoped change with a Conventional Commit message |
| [`write-pr`](skills/write-pr/SKILL.md)           | Fill the PR template into `pr-body.tmp`                   |
| [`make-pr`](skills/make-pr/SKILL.md)             | Push and open the PR against `main`                       |
| [`write-issue`](skills/write-issue/SKILL.md)     | File an issue, with the device details a scrape bug needs |

| Rule                                                | Covers                                               |
|-----------------------------------------------------|------------------------------------------------------|
| [`coding-standards`](rules/coding-standards.md)     | Python, suppressions, tests, dependencies, workflows |
| [`scraper-guardrails`](rules/scraper-guardrails.md) | Location data, the phone, layers, navigation, compat |

## Generated pointers

Tools do not read `.agents/` natively yet, so `tooling/sync_agents.py` (stdlib only) writes a thin
pointer in each tool's native location. A pointer carries the frontmatter and a link, never logic:

```text
.claude/skills/{id}/SKILL.md                    Claude Code skill
.github/skills/{id}/SKILL.md                    GitHub Copilot skill
.cursor/rules/{stem}.mdc                        Cursor rule (alwaysApply: true)
.github/instructions/{stem}.instructions.md     GitHub Copilot instructions (applyTo: '**')
```

Claude Code reads the rules through `CLAUDE.md` → `AGENTS.md`, so it needs no rule pointer.

After adding, renaming or removing a skill or rule, regenerate and commit the pointers:

```bash
make sync-agents    # write pointers, prune orphans
make check-agents   # exit 1 on drift (also a pre-commit hook)
```

Pointers are committed, so a fresh clone works with no build step. No symlinks (not portable) and
no copies (they drift). When a tool reads `.agents/` natively, drop its pointers.

## Scratch files

Skills write drafts to git-ignored `*.tmp` files at the repo root (`pr-body.tmp`,
`issue-body.tmp`), never under `data/` and never into a commit.

## Tool settings

[`.claude/settings.json`](../.claude/settings.json) is hand-authored and committed: it allows the
repo's own check commands so agents do not stop to ask, and denies what the boundaries in
`AGENTS.md` forbid (pushing to `main`, force-push, `--no-verify`, tags and releases, destructive
adb commands, reading `.env`). Personal permissions go in the git-ignored
`.claude/settings.local.json`.
