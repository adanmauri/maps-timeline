---
name: create-branch
description: Create a branch for maps-timeline work from a GitHub issue or a short description, from an up-to-date main. Use when starting a bug fix, feature, docs or chore change.
---

# Create Branch

## Objective

Create a local branch from an up-to-date `main`, named after the issue or the change.

## Workflow

1. Resolve the context from the request:
   - GitHub issue: `42` or `https://github.com/adanmauri/maps-timeline/issues/42`
     (`gh issue view 42` for its title).
   - Plain text: use it as the slug source (e.g. `parser-missing-transit`).
2. Build the branch name:

   | Kind    | Pattern        | Example                          |
   |---------|----------------|----------------------------------|
   | Feature | `feat/<slug>`  | `feat/parser-unconfirmed-visits` |
   | Bug fix | `fix/<slug>`   | `fix/nav-date-drift`             |
   | Docs    | `docs/<slug>`  | `docs/cli-reference`             |
   | Chore   | `chore/<slug>` | `chore/bump-pandas`              |

   With an issue, prefix its number: `fix/42-nav-date-drift`. Slug: lowercase, hyphens,
   alphanumerics only, 3 to 5 words from the title.
3. Check the working tree is clean (`git status --short`); if not, ask before stashing.
4. Create the branch:

   ```bash
   git fetch origin main
   git checkout main
   git pull --ff-only origin main
   git checkout -b <branch-name>
   ```

5. Report the branch name. Push only when the user asks (`make-pr` pushes when it opens the PR).

## Rules

- Short-lived branches, merged to `main` through a pull request; never commit to `main`.
- If the request names neither an issue nor a change, ask for one.
