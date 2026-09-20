# First-attempt additive native range usability

One fresh agent discovered the range/add contract from the unchanged Luda skill
and public tools, completed the requested selection, and verified it semantically.
This is scoped DATA-03 usability evidence, not every native toolkit or virtualized
range acceptance.

The actual GTK3 table has eight visible records in MULTIPLE selection mode;
Record 006 is selected by initial fixture setup. The prompt asks to keep it and
also select the contiguous records Record 002 through Record 004 inclusive,
leaving only those records selected. It does not name `range_end_id`, `extend`, or
a tool sequence. The app writes independent stable integer IDs and every selected
set observed by its selection-change callback.

## First attempt

Run `run-1789899315424105807` used base `b13e5a1` plus the new fixture/evaluator.
Source remained unchanged at fingerprint
`2d774e3fb09c2f3de9c8c64e8a7814c36a9d5516ff31e823fbd58fd8e280d398`.
It completed in **25.100 seconds**, with seven calls and no tool errors:

1. Doctor, windows, activate, inspect.
2. One `desktop_choose` with same-inspection Record 002/004 endpoints and
   `extend=true`.
3. Inspect the visible Selected receipt.
4. Inspect table cells filtered by `states=["selected"]`.

The last complete, nontruncated inspection returned exactly Record 002, 003, 004
and 006, all with selected state and no unreadable branches. The app's independent
final IDs were `[2,3,4,6]`; its event history was `[2,6]`, `[2,3,6]`, `[2,3,4,6]`.
Thus the initial choice was preserved throughout and no other record was
transiently selected. There was no observed ambiguity about additive semantics or
same-inspection endpoints. The only shell action read the installed skill; trace
grading found no hidden-source/oracle access, direct file changes or other tools.
No production code, tool schema, skill or prompt was tuned after the attempt.

## Grader correction, not an agent rerun

The inherited evaluator initially required a screenshot review unconditionally.
The agent instead obtained exact semantic readback and never requested an image.
Its original report therefore remains `passed:false`, with
`workflow_oracle_passed:true` and `range_workflow_discovered:true`. That original
report is retained byte-for-byte. It is not a failed selection or a timeout.

The reusable grader now accepts only a last public inspection of the complete
selected table-cell set, with the exact requested names, selected states,
matching request/response window, `available=true`, `truncated=false`, no name
filter and zero unreadable nodes/branches. It does not accept the agent's final
claim or a dispatched mutation as verification. Wrong/missing/partial results,
name-filtered results, and a later mutation fail the verifier. A separate
hash-bound review parses the original trace under this check; no agent rerun was
performed and no screenshot proof was invented.

The original uncompressed trace SHA-256 is
`b44bf555810df94e47b831481d7d6856f20d3dc7a5420b8c9a74b3a4ebbe1981`.
[Retained evidence](../tests/evidence/agent-native-range-first-attempt/README.md)
includes original report/events/logs and the separate semantic review.

## Cost, scope and reproduction

Backend-reported time summed to 892 ms; wall time also includes model/CLI/transport
work. There were zero images. Codex CLI 0.155.1 reported 140,519 input tokens
(110,720 cached; 29,799 uncached), 436 output tokens and zero separately reported
reasoning tokens. Its resolved model was not exposed in JSON.

The fixture and MCP ran as UID1001 in private Xvfb/D-Bus/XDG/XFWM state. The root
agent reused existing CLI authentication unchanged. Skill-only filesystem access
is an instruction plus trace check, not adversarial filesystem isolation. The
window remains open through the agent's final response; the test then terminates
its owned fixture/session. There are no actual credentials, network application,
or user documents in this task. No browser or shared desktop was used.

A separate preflight before the only agent attempt used actual public MCP to
confirm initial `[6]` and the exact additive event sequence. Five deterministic
grader tests pass. Run in a dedicated provisioned checkout with existing CLI auth:

```sh
uv sync --locked --no-default-groups
# Existing root CLI auth; the harness drops GUI and MCP to silo-desktop.
.venv/bin/python scripts/agent_range_eval.py
```

Fresh runs are new samples, not replacements for retained first attempts. This
small visible native table does not qualify offscreen, changing or recycled
ranges; those have separate runtime refusal/application evidence.
