# Immutable first attempt

`result.json.gz`, `events.jsonl.gz`, `desktop.log.gz` and `stderr.log.gz` are the original unedited attempt artifacts (gzip mtime zero). `review.json` is a separate scoped interpretation, including the complete saved application model and call arguments; it does not replace the original failed strict result. All entered text is authored synthetic fixture data.

The original `passed=false` remains authoritative for strict compliance: the initial read-only `list_mcp_resources` call violated the desktop-only tool rubric. All five independent saved-model checks passed. The unnecessary Ctrl+B dispatch had no formatting effect and is retained in the trace. No retry was performed.

`agent-final-view.png` is the image returned by the agent's last public `desktop_observe`, not a reconstructed illustration. SHA256:

```
a5101592cf44113fce2c6d8052aaef60d2e29d8f2ecad8e2e1779f76a6aabf81
```

See [scope, exact result and reproduction command](../../../docs/AGENT-HARD-BREAK-EVALUATION.md). The retained source inventory binds the attempt; later documentation and import isolation are not claimed to have been evaluated by a second agent run.
