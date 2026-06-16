---
name: create-branch
description: Create a Git branch for maps-timeline work from a GitHub issue or short description ($ARGUMENTS).
---

# Create Branch

Create a local Git branch for work on **maps-timeline**. You provide a GitHub issue
number/URL or a short description ($ARGUMENTS). The branch name follows this repo's
conventions and is created from an up-to-date `main`.

## When to use

Starting work on a bug, parser improvement, or feature. Ensure the working tree is
clean (or stash changes) before branching.

## Steps

1. **Resolve context from $ARGUMENTS**
   - GitHub issue: `42` or `https://github.com/adanmauri/maps-timeline/issues/42`
   - Plain text: use as the slug source (e.g. `parser-missing-transit`)

2. **Build the branch name**

   | Kind | Pattern | Example |
   | --- | --- | --- |
   | Feature | `feat/<slug>` | `feat/parser-unconfirmed-visits` |
   | Bug fix | `fix/<slug>` | `fix/nav-date-drift` |
   | Docs | `docs/<slug>` | `docs/cli-reference` |
   | Chore | `chore/<slug>` | `chore/bump-pandas` |

   Optional prefix when a GitHub issue exists:
   - `feat/42-parser-unconfirmed-visits`
   - `fix/42-nav-date-drift`

   Slug rules: lowercase, hyphens, alphanumerics only, 3–5 words from the title.

3. **Create the branch**

   ```bash
   git fetch origin main
   git checkout main
   git pull --ff-only origin main
   git checkout -b <branch-name>
   ```

4. **Push (optional)**

   ```bash
   git push -u origin <branch-name>
   ```

## Project notes

- Personal OSS CLI tool — prefer **short-lived branches** merged to `main`.
- Parser changes should be testable offline (`parse-file` on saved dumps).
- See [`AGENTS.md`](../../../AGENTS.md) and [`docs/DEVELOPMENT.md`](../../../docs/DEVELOPMENT.md).

If $ARGUMENTS cannot be resolved, ask the user for an issue link or slug.
