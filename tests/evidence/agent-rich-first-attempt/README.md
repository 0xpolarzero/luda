# First-attempt rich-editor agent evidence

Original unmodified CLI JSON events are gzip-compressed with deterministic gzip time. `result-summary.json` keeps the independently saved model, task, grading, metrics, tool errors, usage and source hashes; only the large per-file fingerprint maps are omitted (retained in the original qualification artifacts). All application content is synthetic. CLI authentication was neither read nor exported. The resolved model was not exposed.

The single attempt passed after one safe focus repair. See `docs/AGENT-RICH-CLIPBOARD-EVALUATION.md` for scope and reproduction. No retry, prompt tuning or code change occurred during the attempt. Independent oracle and task grader source are committed with the harness.
