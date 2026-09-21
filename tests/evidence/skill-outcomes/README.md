# Skill outcome correction evidence

The frozen accepted entry skill has SHA-256
`e90eae580e187882b7d6308eb35c77ff19a5a483857a5a0202a52ca7d6f88260`.
All seven reference hashes match baseline `eb268e820a9c96f2c934664b5edb18a0bd416c0a`.
See [evaluation procedure](../../../docs/SKILL-OUTCOME-EVALUATION.md) for the
public/private split, immutable tasks/rubric and acceptance requirements.

`recorded-batch-1.tar.gz` preserves all 17 fresh CLI sessions, exact public prompts,
supplied skill/reference context, source/model/CLI hashes or identities, stdout events,
stderr, final responses, process status and semantic grades. Primary review and a
separate blind review both found 17/17 passes. These are recorded hypothetical GUI
decisions, not executed application workflows.

`interactive-startup-failure.tar.gz` preserves six MCP initialization failures before
any evaluated-agent turn. A venv interpreter symlink was mistakenly resolved to system
Python without dependencies. These runs are unassessable, never passes. The runner
was corrected and tested through actual MCP initialize/list/call before restarting.
Fixture review also aligned inspection filtering and diagnostic response details.

`initial-unit-summary.json` records the initial 1,070-test suite (two skips);
`final-unit-summary.json` records the integrated 1,109-test suite (two skips).
`package-verification.json` records byte comparison of all eight skill files in the
core wheel, source archive, plugin archive and temporary project installation at
commit `61a7a77`. These 0.3.3 package checks are local verification, not a publication.

All evaluated tasks and screenshots are synthetic test material intentionally retained
for reproducibility. No credentials are included. Temporary agent homes/configuration
are removed; existing authentication is accessed by a temporary symlink only. Capture
provenance, real screenshots, independent AT-SPI/xfconf records, cleanup and initial
Thunar capture failure are in `tests/fixtures/skill-outcomes/`.

`interactive-batch-1.tar.gz` preserves the corrected frozen six-case run, including
private state histories, all MCP events/screenshots, exact public prompts, installed
skill hashes, responses, and independent hash-bound semantic adjudication. All six
passed; four explicit unsupported fixture paths were recovered and retained. Together
with recorded batch one this establishes the first new 23/23 batch only.

`recorded-batch-2.tar.gz` and `interactive-batch-2.tar.gz` preserve the repeat 17/17
and 6/6 results, independently reviewed. Hashes establish identical skill, references,
public corpus, runners, fixture and capture manifest between the two completed batches.
The repeat recovered five fixture errors; the negative-effect case's extra unsupported
blank-cell activation and unchanged re-selection are explicitly discussed in its grade.
These two 23/23 batches are not substitutes for the separate live confirmations.

`live-startup-failure.tar.gz` retains the initial actual-Luda MCP launch failure before
any evaluated-agent turn. The wrapper's old `recorded_awaiting_review` label is not a
pass: its nested interaction is explicitly unassessable and both independent settings
are Greybird. A root-only inherited working directory caused a dependency's relative
`.env` stat to fail after dropping privileges. The corrected wrapper changes only the
server working directory and adds a real MCP preflight before the restarted live gate.

`live-mcp-preflight.tar.gz` preserves the corrected initialize/list/doctor preflight
and restrictive-cwd reproduction. `live-confirmation-1.tar.gz` and
`live-confirmation-2.tar.gz` retain two independently accepted fresh actual-Luda runs:
exact task/hash/session/events, independent before/after xfconf+AT-SPI, original PNGs,
final reports, primary/independent reviews and cleanup. Live1 had no MCP errors; live2
recovered one initial diagnostic BUSY error with no effect. Each changed actual theme
from Greybird to Greybird-dark and kept the Style page visible. These are the two new
live passes, distinct from supplied historical claims and from preflight captures.
`resource-cleanup.json` records final disposal of test-created inputs and theme files.

`release-unit-summary.json` records the final candidate check: 1,111 tests,
1,109 passes and two skips, with unchanged source bytes during execution.
