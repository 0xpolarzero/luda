# Application outcome skill correction

The entry skill now requires agents to distinguish selection from application effects,
inspect the affected output, and report incomplete or unverified results accurately.
Selection-only requests still end at selection. Runtime behavior, MCP declarations,
native input, cursor behavior, and all seven technical guides are unchanged.

The source checkout matched the supplied baseline `eb268e820a9c96f2c934664b5edb18a0bd416c0a`.
There were no newer contracts to merge. The exact accepted entrypoint is 1,999 words,
UTF-8 with LF and a final newline, SHA-256
`e90eae580e187882b7d6308eb35c77ff19a5a483857a5a0202a52ca7d6f88260`.
The frozen artifact manifest records all seven reference digests.

## Evaluation material and separation

[Public recorded cases](../tests/fixtures/skill-outcomes/public-cases.json) contain
only the 17 frozen hypothetical session prompts. The separate
[evaluator rubric](../tests/fixtures/skill-outcomes/evaluator-rubric.json) and
[acceptance protocol](../tests/fixtures/skill-outcomes/acceptance-protocol.md)
are evaluator-only material. Never copy them or this document into an evaluated
agent workspace. The protocol preserves the exact six interactive tasks,
transition expectations, rubric interpretations, historical limitations, repeated
gate, and independent live-oracle requirements.

Agent workspaces receive only the candidate skill, its unchanged references,
applicable public tool declarations, and one public task. Archive prompts, hashes,
CLI/model identifiers, events, final answers, process status, independent state,
errors and semantic adjudication in a unique output directory. A completed process
or tool receipt is not a passing grade. No keyword matching can replace semantic
review. Unassessable cases cannot pass. Keep failures and fixture corrections.

Run recorded decisions with the existing authenticated CLI (credentials are neither
printed nor archived):

```sh
.venv/bin/python scripts/evaluation/skill_decisions.py --timeout 180
```

Each invocation creates a fresh batch under `artifacts/skill-decisions/`; every case
uses a separate ephemeral CLI session and temporary HOME, CODEX_HOME and working
directory. The only retained authentication access is a temporary symlink to the
existing local credential file, removed at cleanup. `recorded` means assessable,
not semantically passed. Review each original response against every required and
disqualifying rubric item; preserve the explanation and any adjudication separately.

Run the six reconstructed interactive cases with the checked real capture corpus:

```sh
.venv/bin/python scripts/evaluation/skill_interactions.py \
  --captures tests/fixtures/skill-outcomes/manifest.json --timeout 240
```

The fixture exports the runtime's actual MCP tool declarations, independently tracks
selected/applied/opened state, and archives every attempted call. Unsupported fixture
paths return explicit errors; no fabricated screenshots or implicit selected-to-applied
transitions are used. Only modeled window queries, inspections, observations, target
selection, advertised activation and grounded clicks are supported. Resizing, alternate
targets, keyboard input and unmodeled controls are explicit limitations. A supported,
assessable recovery can pass with its error preserved; unassessable runs cannot pass.
The 20 fixture tests include real screenshot/state correspondence, negative/no-effect
transitions, forbidden opening, stale targets, and MCP initialize/list/call behavior.
This reconstructed harness is not byte-identical to the unavailable historical one.

## Release gate

Require two consecutive unchanged 23/23 batches (17 recorded decisions plus six
interactive cases), followed by two fresh actual-Luda GUI confirmations. Use
`gpt-5.6-sol` without an explicit reasoning-effort override where available.
A different model or CLI is a different evaluation condition. Failures require the
fresh-review/revision procedure in the protocol, not a coached retry or erased
history. Fixture defects require a versioned correction and a restart of the
relevant gate. Unavailable credentials/infrastructure are blockers, not passes.
Do not consume an account reset credit.

For real confirmations, select an explicit ordinary account, private X11 display,
private session bus and disposable application state. Independently reset and read
`xsettings /Net/ThemeName`, capture before/after images, inspect unselected content
and ordinary controls, audit GUI-only task mutations, and confirm page visibility.
Only clean up test-owned processes and files. Shared `:1` tests must hold
`/tmp/luda-live-tests.lock` throughout; private displays avoid disturbing that desktop.

For live confirmation after both complete benchmark passes, use the separate
[private desktop runner](../scripts/evaluation/README-live.md):

```sh
.venv/bin/python scripts/evaluation/skill_live.py \
  --user YOUR_TEST_ACCOUNT --themes /absolute/path/to/extracted/usr/share
```

Run twice in separate invocations, reviewing the first before starting the second.
The theme directory must contain genuine Greybird and Greybird-dark assets. The
account is explicit, never a product default. The runner supplies the same public
appearance task to actual Luda, independently reads before/after xfconf and AT-SPI,
captures screenshots, verifies installed hashes, and retains GUI-only trace audit.
A successful preflight or `recorded_awaiting_review` is not an acceptance pass.

## Supplied historical evidence

The maintainer prompt reports 253 development runs: 187 recorded responses and 66
MCP loops, across the baseline and six revisions. The accepted text passed two
23/23 batches and two real-VM confirmations with `gpt-5.6-sol`, CLI 0.145.0.
It reports 30 simulator tests and metadata validation passing, unchanged references,
and removal of test credentials and the disposable VM. These results were supplied,
not rerun here. Original PNG fixtures and raw events were not supplied.

An earlier revision passed both benchmark batches but failed its first live check
and was rejected. The accepted first benchmark batch contained a rejected alternative
theme selection in the ineffective scenario; subsequent observation and an honest
incomplete report remained assessable. The repeat and accepted live runs had no MCP
errors. This adaptive suite was not held out, and the combined change was not ablated.
No single sentence or general GUI reliability is independently established.

## Local verification

The repository suite initially ran 1,070 tests successfully with two skips.
The accepted artifact and metadata tests verify exact bytes, word count, seven guide
digests, reference links and public/private case pairing. The documented locked
release builder produced separate core/add-on distributions from commit `61a7a77`.
The core wheel, source archive and plugin each contained all eight exact skill files;
a temporary project installation also matched and was removed. These locally built
0.3.3 assets are verification artifacts, not a new published release.

Fresh behavioral gate results and release status are recorded below when assessed.

## New-run failure history

Before any recorded agent ran, the first runner invocation rejected the frozen
`benchmark_name` metadata. The schema validator was corrected and regression-tested;
the public tasks and rubric were unchanged. The first six interactive launches then
failed MCP initialization before any agent turn: resolving the venv interpreter
symlink selected system Python without the fixture dependencies. All six remain
unassessable, with original stderr/events/results preserved. This is a harness defect,
not a Luda runtime or skill failure; the affected interactive gate must restart after
the corrected runner is frozen and tested. Before that restart, review also corrected
filtered-inspection parent IDs and public numeric-bound/doctor-response details to
match the runtime. These are versioned fixture corrections, not waived failures.

After integrating the runners, the repository suite passed 1,109 tests with two skips.
The source fingerprint remained unchanged during this run.

The first newly completed acceptance batch passed 23/23: 17 recorded decisions
and six interactive cases. Recorded decisions received primary and independent
semantic review; interactive cases received independent state/trace/final-claim
review. Four explicit fixture errors were recovered: three depth-limited inspections
and one unsupported wait. Every required result remained assessable; all errors and
original responses are retained. This is new CLI 0.155.1 evidence, separate from the
supplied CLI 0.145.0 historical results.

The repeat batch also passed 23/23 with the same recorded runner, public corpus,
skill/reference hashes, interactive runner, fixture and captures. It retained five
recovered fixture errors. In the no-effect case, an unsupported blank-cell activation
had no effect; a final supported re-selection also left state unchanged. Its final
report remained accurately incomplete/light. The frozen criteria do not require an
extra screenshot after every no-change action. This caveat is preserved in the
independent semantic grade rather than hidden as an error-free run.

The first live launch was unassessable before an evaluated-agent turn: privilege
dropping left the MCP server in a root-only temporary working directory, and its
settings dependency could not stat the relative `.env` path. Direct reproduction
confirmed the permission error. Initial/final independent state remained Greybird;
there were no agent tool events or final answer. The live wrapper is corrected to
enter its own ordinary-account private directory before starting Luda, and must
preflight real MCP initialize/list/doctor from the same restrictive launch context.
This live-harness correction leaves the frozen benchmark runners and skill unchanged;
the live gate restarts. The original startup evidence is retained, never counted as a
live confirmation or silently treated as an error-free run.
