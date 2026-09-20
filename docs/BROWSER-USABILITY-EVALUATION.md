# Fresh-agent owned-browser usability probe

This is a bounded synthetic first-use evaluation, not universal web qualification.
Runtime source was unchanged commit `e78adabc7d5b05ac71cf58b3b8d06131bb9db1cd`.
Before the first workflow, the evaluator read only `AGENTS.md`, the public
`skills/luda/SKILL.md`, `docs/TOOLS.md`, and `docs/OWNED-BROWSER.md`; it used CLI
help and registered MCP schemas, without reading implementation or existing tests.
The skill's temporary lifetime guidance was sufficient: this browser/profile and
unsaved content disappear when the MCP connection ends. The independent fixture
writes submitted data outside that profile before disconnect.

## First workflow and independent result

Run `artifacts/browser-usability/1789888525393488620` used ordinary UID 1001,
a private Xvfb display selected with `-displayfd` (`:0`), private session D-Bus,
XFWM, Playwright 1.63.0 and actual sandbox-enabled Chromium 153.0.8010.12.
It did not attach the shared desktop or use a real account/profile.

The sequence was doctor → open temporary browser → activate → inspect → type
Reference → type Message → select code points `[1,2)` → insert replacement →
read text → inspect named Submit button → invoke its observed `press` action →
find Submitted window → try the obsolete field once → disconnect.

All intended first-workflow calls succeeded. The deliberate stale-target call
returned `STALE_TARGET`, `effect="none"`, with guidance to inspect again. The
button exposed multiple actions, so following the skill and selecting the exact
observed `press` action avoided guessing or silently choosing a default.

The request values were known synthetic literals:

```python
reference = "R-東京-😀"
initial_message = "A😀B café é\t東京\nsecond line\n\n"
replacement = "🧪Ω"  # replaces one astral code point, offsets [1,2)
expected_field = "A🧪ΩB café é\t東京\nsecond line\n\n"
```

Tool readback was exactly `expected_field` (29 code points), with the caret at
3 and no selection. Only after the complete tool sequence did the evaluator read
the authoritative HTTP fixture output. It contained exactly the expected
Reference and Message; ordinary HTML URL-encoded submission serialized each LF
as CRLF. `submission.json` preserves the actual raw percent-encoded request and
decoded CRLF values; it does not silently normalize them. No oracle values were
used to aim input, and no DOM injection or value setter fixed the fixture.

The browser PID 25720 was absent and its observed temporary profile
`/tmp/silo-desktop-1001/owned-browser-lrraqasz` was removed after disconnect.
This checks this normal disconnect only. It does not retest subsequent download
cleanup fixes, abnormal termination, or every possible descendant process.

Every MCP request and full response is in `trace.jsonl`; `schemas.json`,
`metadata.json`, `submission.json`, and `verification.json` preserve the public
contract, source identity, fixture hash and assertions. Synthetic artifacts are
ignored by the existing repository artifacts rule.

## Friction and concrete follow-ups

1. Unfiltered inspect returned 150 mostly browser-chrome nodes before the two
   useful `text_fields`, creating about 19,600 output tokens and truncating the
   native tree. The public name/role filters worked. Put `text_fields` and their
   coverage before native nodes in owned-browser responses, and add a short
   skill example using `desktop_inspect(window_id, role="entry")` for fields,
   followed by a name filter for the submit button. This is presentation guidance,
   not a request to drop accessible native controls.
2. The input and textarea both advertise `role="entry"`, `interfaces=["Text"]`
   and identical actions. Public docs explain single-line LF/tab rejection, but
   inspect does not distinguish their accepted shapes. Add explicit `multiline`
   or `html_tag`/`input_type` capability metadata, avoiding a caller's need to
   infer this from names or try invalid input.
3. Responses provide JSON inside MCP text with `structuredContent=null`.
   This works, but a client needs an extra JSON parse and cannot use a declared
   output shape. Consider structuredContent/outputSchema while retaining text
   compatibility. This did not block the workflow.
4. During the later scripted reproduction, the plausible
   `desktop_wait(condition="window_present", text="Submitted")` was refused:
   `INVALID_ARGUMENT: Window conditions require only window_id.` The public
   signature and description do not state that conditional requirement. Add a
   per-condition argument matrix and say that title discovery uses
   `desktop_windows(query=...)`; window waits require an existing window ID.
   The first interactive workflow already used that successful discovery path.

No production code, schemas, or skill were changed for this evaluation.

## Reproduction and preserved failures

Provision this worktree's environment with `uv sync --locked --extra browser`.
Make `artifacts/browser-usability` writable by `silo-desktop`, then run:

```sh
runuser -u silo-desktop -- dbus-run-session -- \
  .venv/bin/python scripts/evaluation/browser_usability.py --scripted
```

The harness binds a loopback HTTP server on an ephemeral port, creates a private
Xvfb/XFWM desktop, starts the MCP server, saves exact requests/responses, and
asserts tool readback and independently submitted values. Without `--scripted`,
send one JSON object `{"name":"desktop_doctor","arguments":{}}` per stdin
line and `quit` to disconnect. It prints the fixture URL and artifact directory.
The environment-specific Chromium path is intentionally explicit in the harness.

All failures remain distinct from the first workflow's success:

- Setup runs `1789888510667409113` and `1789888518766569326` failed before MCP:
  Git rejected root-owned worktree metadata for the ordinary account; the first
  repair command also used unavailable `python` instead of `python3`. The final
  harness uses per-command `safe.directory` and resolves source before X startup.
- Scripted run `1789888616385576039` failed in the evaluator helper because its
  `name` argument collided with `desktop_inspect(name=...)`. Its trace remains;
  `scripted-first-failure.log` preserves the stack. Rename the helper parameter
  to `tool_name` fixed this harness error.
- Scripted run `1789888630422801212` preserved the window-wait argument refusal
  above, with trace and `scripted-wait-failure.log`; submission had already
  happened. The corrected harness uses the original observed-window workflow.
- Scripted run `1789888671870300440` completed, including exact readback,
  independent CRLF submission assertion and stale-target refusal. Its
  `verification.json` records those three assertions. Runtime source remained
  the original commit throughout; harness changes are separate.

The initial Git failures were preserved in evaluator tool transcripts and their
run directories; no full console capture was active for those two startup runs.
