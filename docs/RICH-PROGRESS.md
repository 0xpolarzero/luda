# Rich-editor partial progress

> Historical record from before Editor Bridge became a separate add-on. Tool names, source paths and test commands below describe the recorded revision, not the current core installation. For current setup and supported behavior, see [Editor Bridge](../addons/editor-bridge/README.md).

When a valid rich-text segment plan reaches the worker, its final reply can carry
`progress` on success or `details.progress` on error. This is fixed metadata:

```json
{
  "unit": "rich_text_segment",
  "requested": 3,
  "verified_completed": 1,
  "current_uncertain": 1,
  "not_started": 1,
  "application_commit_verified": false
}
```

One segment is a requested piece between LF separators, including empty pieces.
For later segments, its paragraph-break action belongs to that segment. A segment
is completed only after all its actions have passed exact text, paragraph,
unaffected-formatting and caret readback. `verified_completed` records those
historical checks, not a guarantee that the document has remained unchanged
since them. `application_commit_verified=false` means no save, autosave or
application-level commit was verified; it does not negate the actual readback.

`current_uncertain` is zero or one. It includes an attempted but not fully
verified segment, including a verified paragraph break followed by a failed text
step. With clipboard transport, publication alone can make the current segment
uncertain before any paste; the separate `clipboard_may_have_changed` flag still
applies. `not_started` counts remaining content segments, not preparatory focus or
selection operations. The three counts sum to `requested`, bounded by the same
27-segment limit used by the input planner. A preflight failure after planning
can therefore report zero completed, zero uncertain and all segments not started.
Failures before a valid plan exists may omit progress.

These are final-receipt counts, not a progress stream, transaction checkpoint or
resume API. Lost replies, controller cancellation and worker death do not cause
invented counts. A final worker timeout receipt may contain progress; a parent
transport timeout without that receipt cannot. Inspect the current document and
choose the next action explicitly. Never replay a remainder automatically.

The worker emits no input text, offsets, model, segment lengths or exception
messages in this metadata. Browser transport validates the exact field set,
integer types, total, segment unit and original requested count; it does not
accept a browser-supplied key-progress record. Public serialization, operation
history and sanitized reports apply a strict unit-discriminated projection.
Malformed metadata is dropped. Key-chord progress keeps its existing separate
meaning: dispatch counts are not rich-text readback counts.

## Evidence

Eleven focused tests cover a verified native segment followed by rejected text,
preflight refusal before the next segment, intermediate key-release exception,
clipboard staging without paste, held-input refusal after a completed segment,
malformed metadata, actual final-receipt IPC, lost receipt without fabricated
progress, public/history/report projection, and a malformed subsequent packet
that must not reuse the previous request's progress. Existing 28 rich-text,
six key-progress and 12 report tests also passed.

`tests/live_rich_progress.py`, matrix suite `rich-progress`, serves the existing
real ProseMirror application plus an ordinary trusted-key handler that rejects
Enter. All mutation goes through public MCP. The first segment is entered and
verified; the second segment's native paragraph action is rejected; the third
never starts. Independent application model/callback evidence agrees for both
native and clipboard transports. The public error retains uncertainty and the
expected counts, while error/status/report outputs contain none of the input
markers. No provider setter or model-editing script supplies the text.

The final UID1001 private Xvfb/XFWM/D-Bus run passed **14 checks** in **5.378s**
with unchanged source and no owned survivors, Chromium 153.0.8010.12 on Ubuntu
24.04 ARM64. [Retained results](../tests/evidence/rich-progress/result.json)
include the initial harness failure (`history` was incorrectly guessed instead
of the actual status field `operations`) and both complete runs. No lost-receipt
cancellation progress or general application recovery is qualified.
