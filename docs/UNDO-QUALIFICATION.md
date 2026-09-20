# Native editor undo grouping

`tests/live_undo.py` characterizes semantic whole-field replacement in actual
Mousepad 0.6.1. It uses public Desktop operations, then deliberate native keyboard
Undo/Redo. Each observed state is explicitly saved to an owned temporary file;
independent disk bytes must match public text readback. No user document is used.

```sh
.venv/bin/python scripts/qualification_matrix.py --suites undo
```

The first ordinary-UID ARM64 run passed in 4.113 seconds. The observed sequence was:

| Operation | Stored document |
|---|---|
| Semantic replacement and explicit Save | Exact replacement, including Hebrew, emoji, LF and tab |
| First Undo | Empty document |
| Second Undo | Exact original Japanese multiline document |
| First Redo | Empty document |
| Second Redo | Exact replacement |

Thus one semantic replacement produced **two application undo steps** here.
A verified replacement is not a promise of one atomic undo operation. The tool
has no generic transaction/grouping interface to each application's undo manager.
Agents should observe after Undo, especially before another Save. These particular
explicit saves are independent test oracles, not a recommended recovery workflow.

Evidence: `artifacts/qualification-matrix/run-1789874767531346349`, unchanged
source fingerprint `c215097e18cf431ffd8e85e21564314925276454b6680a30adfda5085e923f7b`, with no owned survivors.
The test records grouping instead of imposing a universal grouping policy. It
requires the final Redo sequence to restore the replacement and file/readback
agreement at every step. Other toolkits, typing routes, editor settings, user edits
interleaved with agent input and undo history eviction need their own evidence.
Catalog EDIT-06 remains release-unqualified.
