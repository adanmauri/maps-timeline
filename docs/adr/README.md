# Architecture Decision Records

One file per decision: `NNNN-<kebab-slug>.md` whose first line is `# NNNN. <Title>`, numbered
sequentially and never renumbered. A superseded ADR stays in place with its status changed and a
link to its successor. Start from [`template.md`](template.md).

The ADR holds the rationale; the rules in [`.agents/rules/`](../../.agents/rules/) hold the
checklist and cite the ADR instead of repeating it, and the guides in `docs/` describe the current
state without sending the reader here. `make check` fails on a numbering gap, a heading that
disagrees with its file name, an ADR missing from this index, or a broken relative link anywhere
in the docs. A number taken by a branch that has not merged yet goes under **Reserved** so it is
not reported as a gap.

| ADR                                                                            | Title                                                           | Status   |
|--------------------------------------------------------------------------------|-----------------------------------------------------------------|----------|
| [0001](0001-the-scraper-reads-the-timeline-from-the-accessibility-tree.md)     | The scraper reads the Timeline from the accessibility tree      | Accepted |
| [0002](0002-raw-capture-and-normalization-are-separate-stages.md)              | Raw capture and normalization are separate stages               | Accepted |
| [0003](0003-parsing-works-on-the-xml-never-on-the-device.md)                   | Parsing works on the XML, never on the device                   | Accepted |
| [0004](0004-the-day-comes-from-date-arithmetic-the-header-only-verifies-it.md) | The day comes from date arithmetic; the header only verifies it | Accepted |
| [0005](0005-the-official-export-is-merged-by-time-overlap-and-place-id.md)     | The official export is merged by time overlap and place ID      | Accepted |
| [0006](0006-the-official-export-plans-the-walk-and-every-run-counts.md)        | The official export plans the walk, and every run counts        | Accepted |
| [0007](0007-location-data-never-leaves-the-users-machine.md)                   | Location data never leaves the user's machine                   | Accepted |
| [0008](0008-uv-is-the-development-toolchain.md)                                | uv is the development toolchain                                 | Accepted |
| [0009](0009-quality-gates-pre-commit-locally-megalinter-in-ci.md)              | Quality gates: pre-commit locally, MegaLinter in CI             | Accepted |
| [0010](0010-agent-assets-live-in-agents-with-generated-pointers.md)            | Agent assets live in `.agents/` with generated pointers         | Accepted |
| [0011](0011-non-python-linter-versions-follow-the-megalinter-image.md)         | Non-Python linter versions follow the MegaLinter image          | Accepted |
| [0012](0012-pull-requests-check-what-they-change-main-checks-everything.md)    | Pull requests check what they change; main checks everything    | Accepted |
| [0013](0013-actions-are-pinned-to-a-commit.md)                                 | Actions are pinned to a commit                                  | Accepted |

## Reserved

None.
