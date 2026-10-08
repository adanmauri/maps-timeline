# Contributing to maps-timeline

Thank you for your interest in contributing to maps-timeline! This document covers the
contribution process. How to set up, check and change the code is in
[docs/DEVELOPMENT.md](docs/DEVELOPMENT.md), and the binding standards are in
[`.agents/rules/`](.agents/rules/).

## Your data stays yours

The Timeline is a person's location history, and this repository is public. Never attach an
official export, a run from `data/`, or a dump or screenshot from a real phone to an issue or a
pull request. When a dump is the only way to show a parser problem, replace the place names and
addresses first and say it is anonymized.

## Getting Started

1. Fork the repository
2. Clone your fork: `git clone https://github.com/<your-user>/maps-timeline.git`
3. Set up the development environment (needs [uv](https://docs.astral.sh/uv/)):

   ```bash
   make setup   # uv sync --locked, then installs the git hooks
   ```

## Reporting Issues

- Before opening a new issue, search for existing issues to avoid duplicates
- Use the issue forms: a bug report asks for the command, its output, and, for a problem on the
  phone, the device, Android and Google Maps versions
- Many parser problems are easiest to show with an anonymized dump: `maps-timeline dump` saves
  the current screen, and `maps-timeline parse-file` reproduces the problem from it

## Contributing Code

### For New Contributors

If you're new to the project and would like guidance on where to start, feel free to:

- Open an issue asking for suggestions
- Comment on existing issues to express interest
- Start with small improvements like documentation, a parser edge case with a synthetic dump, or
  a test

### Development Workflow

1. Create a branch from an up-to-date `main`: `feat/...`, `fix/...`, `docs/...` or `chore/...`
2. Make your changes following the [coding standards](.agents/rules/coding-standards.md) and the
   [scraper guardrails](.agents/rules/scraper-guardrails.md)
3. Add or update tests; `maps_timeline/` stays at 100% coverage (see
   [Testing](docs/DEVELOPMENT.md#testing))
4. Run `make check` until it passes; the commit hook runs the same linters on staged files
5. Commit with [Conventional Commits](https://www.conventionalcommits.org/):
   `fix(parser): read unconfirmed visits`, `feat(cli): add --until`
6. Push to your fork and open a Pull Request. The first time you contribute, a maintainer
   approves the CI run before it starts.

A change to selectors, navigation or the walk also needs a short run on a real phone, described
in [`AGENTS.md`](AGENTS.md#verification); say in the pull request what you ran and on which phone.

### Pull Request Guidelines

- **All PRs should be opened against the `main` branch**
- Fill the PR template; under Test plan, list only what you actually ran
- Aim for atomic commits (one logical change per commit)
- If your PR breaks the raw JSONL, a command or option, or the dataset columns, say so in the title
  with `!` (`feat(cli)!: ...`) and explain it under Breaking change
- Keep PRs focused: avoid mixing unrelated changes
- If a PR is not ready for review, mark it as a Draft
- Update the README and `docs/` when you change behavior

### Git Best Practices

- Avoid working directly on the `main` branch of your fork
- Use `git add -p` to stage changes selectively
- If conflicts arise, prefer `git rebase` over `git merge` to keep history clean
- When linking to code in discussions, use GitHub's permalink feature (press `y` while viewing code)

### Decisions

A change that reverses or extends a recorded decision (how the app is read, the two stages, the
merge, the planner, the toolchain, the quality gates) comes with a new ADR in
[docs/adr/](docs/adr/README.md), from the template there.

## Code Review Process

1. The maintainer reviews every pull request before merging; the checks must pass
2. Reviews look at:
   - Adherence to the coding standards and the scraper guardrails
   - Code quality and correctness
   - Test coverage
   - Documentation updates
3. Address review comments promptly
4. Keep discussions focused and constructive

## Questions?

If you have questions or need help, feel free to:

- Open an issue
- Comment on existing issues or PRs

Thank you for contributing to maps-timeline!
