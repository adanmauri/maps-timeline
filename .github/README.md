# GitHub configuration

| Path | Purpose |
| --- | --- |
| [`.agents/skills/`](../.agents/skills/) | **Source of truth** for project agent skills |
| [`.cursor/skills/`](../.cursor/skills/) | Stubs → `.agents/skills/` (Cursor IDE) |
| [`.cursor/rules/`](../.cursor/rules/) | Cursor rules → `AGENTS.md` |
| [`workflows/`](workflows/) | CI: tests, quality, security, release |
| [`PULL_REQUEST_TEMPLATE.md`](PULL_REQUEST_TEMPLATE.md) | Default PR body |

Do not duplicate skill content outside `.agents/skills/`. See [`.agents/README.md`](../.agents/README.md).
