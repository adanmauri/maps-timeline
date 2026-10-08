# Checks and CI

What checks a change, where, and why. Setup and commands are in [DEVELOPMENT.md](DEVELOPMENT.md).

## Two layers

- **Locally, pre-commit:** [`.pre-commit-config.yaml`](../.pre-commit-config.yaml) runs on the
  staged files at every commit, and on the whole repository with `make lint` and `make check`.
  Feedback comes before the push, and `make check` is the single command that says a change is
  done.
- **In CI, MegaLinter and the workflows:** MegaLinter runs the same linters, plus scanners that
  need the network or a vulnerability database; the workflows run the tests and a daily security
  scan.

Every linter MegaLinter runs on files offline is also a local hook, so a commit that passes the
hooks passes the same linters in CI.

| Tool                                   | Checks                                                                        |  Local hook  | CI                                        |
|----------------------------------------|-------------------------------------------------------------------------------|:------------:|-------------------------------------------|
| pre-commit-hooks                       | whitespace, end of file, YAML, TOML, large files, merge markers, private keys |     yes      |                                           |
| betterleaks, secretlint                | secrets in the repository                                                     |     yes      | MegaLinter                                |
| uv-lock                                | `uv.lock` matches `pyproject.toml`                                            |     yes      | `uv sync --locked` fails                  |
| Black, isort                           | formatting, import order (Black profile, 100 columns)                         |     yes      | MegaLinter                                |
| Ruff, Flake8, Pylint                   | lint                                                                          |     yes      | MegaLinter                                |
| mypy, Pyright                          | types                                                                         |     yes      | MegaLinter                                |
| Bandit                                 | security issues in `maps_timeline/`                                           |     yes      | MegaLinter, `security.yaml`               |
| actionlint                             | workflow syntax and expressions                                               |     yes      | MegaLinter                                |
| zizmor                                 | security of the workflows and `dependabot.yaml`                               |     yes      | MegaLinter                                |
| markdownlint, markdown-table-formatter | Markdown style and table layout                                               |     yes      | MegaLinter                                |
| yamllint, prettier, jsonlint           | YAML and JSON syntax and formatting                                           |     yes      | MegaLinter                                |
| cspell                                 | spelling (project words, and the Spanish UI strings, in `.cspell.json`)       |     yes      | MegaLinter                                |
| jscpd                                  | copied code                                                                   |     yes      | MegaLinter                                |
| `tooling/sync_agents.py --check`       | agent pointers in sync with `.agents/`                                        |     yes      |                                           |
| `tooling/check_docs.py`                | relative links in Markdown, ADR numbering and index                           |     yes      |                                           |
| `tooling/check_commit_msg.py`          | no tool attribution in the commit message                                     |  commit-msg  |                                           |
| pytest                                 | tests on 3.14 with 100% coverage, and on 3.13                                 | `make check` | `tests.yaml`                              |
| Trivy, Grype, OSV-Scanner, checkov     | vulnerable dependencies, misconfigured workflows                              |              | MegaLinter; Trivy also in `security.yaml` |
| trufflehog                             | verified secrets                                                              |              | MegaLinter                                |
| lychee, v8r                            | broken links, files that do not match their JSON schema                       |              | MegaLinter                                |

No check can run the app: behavior on a real phone is verified by hand, as
[`AGENTS.md`](../AGENTS.md#verification) describes.

## Every linter blocks

Every active linter fails the build on a finding, formatters included: MegaLinter treats formatter
findings as warnings by default, and [`.mega-linter.yml`](../.mega-linter.yml) turns that off
(`FORMATTERS_DISABLE_ERRORS: false`). A linter that does not fit this repository is disabled there,
with the reason, never left running without blocking: a finding that never fails the build is never
fixed. Each setting in that file has a comment.

## Same settings, and mostly the same versions

**Settings.** When a repository has no config file by the name a linter looks for, MegaLinter uses
its own default (a `.pylintrc`, a `.ruff.toml` with line length 88...), so the same linter would
report different things locally and in CI. To avoid it, `.mega-linter.yml` points the Python
linters at `pyproject.toml`, and the other linters' settings live in the repository: `.flake8`,
`.cspell.json`, `.markdownlint.json`, `.yamllint.yml`, `.secretlintrc.json` and `.jscpd.json`. Both
sides read the same files. MegaLinter's pre-commands install the runtime
dependencies, the `test` group, the stubs and the `pylint-pydantic` plugin from `uv.lock` where
mypy, Pylint and Pyright need them.

**Versions.**

- The **Python linters** are ordinary development dependencies: unpinned in `pyproject.toml`,
  locked in `uv.lock`, updated by Dependabot. They can differ from the versions in the MegaLinter
  image, and while they do, a Python linter can disagree between the hooks and CI.
- The **other hooks** must name a version anyway, so they name the image's: in
  `additional_dependencies` for the Node.js packages, as `rev` for betterleaks, actionlint and
  zizmor. pre-commit installs the Node.js and Go runtimes they need.

**Bumping MegaLinter** is manual: CI runs its image by digest, and Dependabot does not update
`docker://` references.

1. Pick a release from [MegaLinter's releases](https://github.com/oxsecurity/megalinter/releases),
   at least 14 days old, and read its changelog for breaking changes.
2. Get the image digest: `docker buildx imagetools inspect ghcr.io/oxsecurity/megalinter-python:vX.Y.Z`
   prints it as `Digest:`.
3. Update the `uses: docker://ghcr.io/oxsecurity/megalinter-python:vX.Y.Z@sha256:...` line in
   `code-quality.yaml`, tag and digest together.
4. Read the versions in the release's Dockerfile (`flavors/python/Dockerfile` in the MegaLinter
   repository, at the tag) and update the non-Python hooks in `.pre-commit-config.yaml` to match.
5. Run `make check`, fix what the new versions report, and push it all in one pull request.

Nothing checks the hook versions automatically.

## What a pull request checks

A pull request checks what it changes; a push to `main` checks everything.

- **MegaLinter** lints only the files that differ from `main` (`git diff origin/main...`). The
  checkout fetches the whole history, which that diff needs.
- **Exception:** a pull request that changes a linter's settings (`.mega-linter.yml`,
  `.pre-commit-config.yaml`, `pyproject.toml` or any of the config files above, or
  `code-quality.yaml`) lints everything. Otherwise a stricter rule would be checked against the
  config file alone, pass, and then fail on `main`.
- **Scanners always see everything.** Trivy, Grype, OSV-Scanner, Syft, betterleaks, secretlint,
  trufflehog, checkov and jscpd scan the whole repository by design; MegaLinter cannot narrow them.
- **Tests** run in full whenever they run, because a change in one module can break another.
  Pull requests that touch none of `maps_timeline/`, `tests/`, `pyproject.toml`, `uv.lock`,
  `.python-version` or `tests.yaml` skip them; `main` always runs them. A first job, `changes`,
  makes that call, so the `test` and `test-compat` checks still report (as skipped, which counts
  as passing) instead of staying pending, as a `paths:` filter would.
- **Locally**, the hooks check the staged files, but mypy, Pyright, Pylint and Bandit check the
  whole project whenever a Python file changes.

The cost: a pull request can pass and `main` fail, on a check that spans files or on a file the
pull request did not touch; the fix goes in the next pull request.

## Merging to main

A repository ruleset ("Main Branch Protection") guards `main`:

- Changes reach it only through a pull request, never by a direct push, a force-push or a
  deletion.
- The `megalinter`, `trivy`, `bandit`, `test` and `test-compat` checks must pass, on a branch that
  is up to date with `main`.
- The history stays linear: squash or rebase, no merge commits.
- No approval is required, so the maintainer merges once the checks pass. Admins can bypass the
  ruleset, for an emergency only.


## Workflows

| Workflow             | Runs on                                                                | Jobs                                                                                                              |
|----------------------|------------------------------------------------------------------------|-------------------------------------------------------------------------------------------------------------------|
| `tests.yaml`         | push to `main`; PRs that touch the code, the tests or the Python setup | tests on 3.14 with the 100% coverage gate the README's badge states; tests on 3.13                                |
| `code-quality.yaml`  | push and PR to `main`                                                  | MegaLinter (Python flavor): the changed files on PRs, everything on `main` and on PRs that change linter settings |
| `security.yaml`      | push and PR to `main`, daily                                           | Trivy (results in the Security tab, except from PRs) and Bandit (report in the job summary); neither blocks       |
| `todo-to-issue.yaml` | push to `main`                                                         | turns `TODO` and `FIXME` comments in code into issues                                                             |
| `release.yaml`       | started by hand from the Actions tab                                   | builds the wheel and the sdist and creates a draft release pinned to the commit (see DEVELOPMENT.md, Releasing)   |

Every workflow starts with no permissions (`permissions: {}`), and each job asks for what it needs.
Only one job can write: the release draft. No job pushes to the repository.

## Actions are pinned to a commit

Every `uses:` names a commit SHA, with the version in a comment:

```yaml
uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
```

A tag such as `v7.0.1` is a label its owner, or anyone with the owner's credentials, can move to
other code; a major tag such as `v7` moves on purpose with every release. Either way, the workflow
would run new code with no change in this repository. A SHA is the hash of the code itself and
cannot point anywhere else. In March 2026 an attacker moved almost every tag of
`aquasecurity/trivy-action` to code that steals the runner's secrets.

- zizmor enforces the pins, as a local hook and in MegaLinter.
- Dependabot updates the actions monthly, for releases at least 14 days old, moving the SHA and
  the comment together.
- A tool an action downloads is pinned too when the action allows it: `security.yaml` sets the
  Trivy binary's version.
- Every checkout drops its credentials (`persist-credentials: false`).
- Container images run by digest: MegaLinter runs as
  `docker://ghcr.io/oxsecurity/megalinter-python:v10.1.0@sha256:...`. Dependabot does not update
  `docker://` references, so MegaLinter is bumped by hand (above).
