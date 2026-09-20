# First attempt: synthetic owned password entry

See [the scoped evaluation](../../../docs/AGENT-OWNED-SECRET-EVALUATION.md).
`result.json.gz` and `events.jsonl.gz` preserve the original single attempt,
including its `passed:false` pending image review. `visual-review.json` records
later inspection of the exact final image, without altering that report.
`cleanup-review.json` records bounded post-run process/profile observations.

The client trace and prompt deliberately contain a fixed **synthetic** password.
No actual credentials, accounts or auth configuration were used as test data.
App oracles retain hashes/counters only; tool responses do not echo the secret.

The preflight script/logs are separate setup validation. The initial log preserves
an argument-name collision before entry, fixed before the only agent attempt.
The preflight script records its original worktree location for reproducibility;
it is not an installed product entry point. No source or skill changes were made
to make the agent choose a preferred sequence.
