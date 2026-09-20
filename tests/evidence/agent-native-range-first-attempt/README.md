# First attempt: preserve a choice while adding a native range

[Evaluation and limits](../../../docs/AGENT-NATIVE-RANGE-EVALUATION.md).
Original `result.json.gz`/`events.jsonl.gz` remain unchanged. The original image-only
gate reports `passed:false`, although both independent workflow and range-discovery
checks passed. The agent verified a complete selected-cell set through public
accessibility, without requesting an image. `semantic-review.json` records a later
explicit parser review against the original trace hash. No agent rerun occurred.
Preflight is separate setup validation, not an agent attempt. Its script retains
its original worktree path. No actual credentials or user data appear here.
