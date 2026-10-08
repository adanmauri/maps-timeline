# 0010. Agent assets live in `.agents/` with generated pointers

**Status:** Accepted · **Date:** 2026-10-08

## Context

`AGENTS.md` held everything an agent needed in one file of about 400 lines: the project context,
the layout, the code standards, the suppression policy, the CLI usage and the guardrails. Skills
lived in `.agents/skills/`, with hand-written stubs in `.cursor/skills/` and a Cursor rule that
summarized `AGENTS.md`. Claude Code and GitHub Copilot had no entry point of their own, and the PR
and issue templates existed twice: in the skills and under `.github/`. The owner's other
repositories keep one canonical copy of each asset and generate the rest.

## Options

- **One file per tool, written by hand:** simple, but a copy of every rule per tool.
- **Symlinks from each tool's location:** one copy, but not portable (Windows, some tools ignore
  them).
- **One canonical copy in `.agents/`, with thin generated pointers per tool:** one copy, portable,
  and drift is detectable by a script.

## Decision

- [`AGENTS.md`](../../AGENTS.md) at the root is the canonical manual ([agents.md](https://agents.md/)
  standard), short: what the repo is, what to read, the layout, the workflow, what must pass, how
  to verify on a phone, the boundaries and the skills. `CLAUDE.md` and
  `.github/copilot-instructions.md` are hand-written pointers to it.
- The binding checklists move to rules in `.agents/rules/` (`coding-standards`,
  `scraper-guardrails`), which cite the ADRs instead of repeating them. Skills stay in
  `.agents/skills/`, following the [`.agents` protocol](https://dotagentsprotocol.com/) with
  `SKILL.md` spelled for Claude Code.
- `tooling/sync_agents.py` (standard library) writes a pointer per tool: `.claude/skills/`,
  `.github/skills/`, `.github/instructions/`, `.cursor/rules/`. Pointers carry frontmatter and a
  link, never instructions, and are committed so a fresh clone works without a build step.
  `make check-agents`, also a pre-commit hook, fails on drift.
- The PR and issue templates live once, under `.github/`; the skills fill them.
- `.claude/settings.json` allows the repo's check commands and denies what the boundaries forbid.
- No tool is credited in commits, PRs or docs; a commit-msg hook (`tooling/check_commit_msg.py`)
  rejects attribution lines.

## Consequences

### Positive

- One place to edit a rule or a skill, and every tool sees the change after `make sync-agents`.
- The same layout as the owner's other repositories, so moving between them costs nothing.

### Negative / trade-offs

- Generated files in four directories, which must not be edited by hand.
- When a tool reads `.agents/` natively, its pointers become dead weight to remove.

### Follow-ups

- [`.agents/README.md`](../../.agents/README.md) holds the operating procedure and cites this ADR.
