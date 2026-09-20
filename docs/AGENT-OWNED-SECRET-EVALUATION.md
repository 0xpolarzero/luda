# First-attempt owned password-entry usability

The unchanged Luda skill and public tools were available. The prompt asked the
agent to open a temporary browser at an owned loopback HTTP form, replace Password
with an exact synthetic string containing a tab, Japanese and joined emoji, avoid
clipboard and submission, and verify the visible receipt. It did not name
`desktop_type_secret`, give a focus sequence, or reveal fixture/oracle paths.
No skill or runtime change was made to improve this attempt.

## Result and discoverability

Run `run-1789898524358428097` used base `65c6fcc` plus the new evaluator/fixture.
Its source fingerprint remained
`163243b079972a9e62a0841fe5d448085c56f203d8012337c252d23c72ca54c5`
throughout the run. The five calls were:

1. `desktop_doctor`
2. `desktop_open_browser`
3. `desktop_inspect(role="entry")`
4. `desktop_type_secret`
5. `desktop_observe`

The inspected password reported ordinary `supported=false`,
`unsupported_reason=PROTECTED_FIELD`, and `secret_entry_supported=true`.
The agent correctly chose the explicit secret path directly. It neither tried
ordinary focus nor ordinary typing, and did not read the password. All five tool
responses omitted the synthetic secret marker. The only shell command read the
installed skill. No hidden file, app source, oracle or direct DOM access appeared
in the agent trace.

The independent app oracle recorded the expected SHA-256, exactly one input
event, zero paste events, zero submissions, unchanged reference-field hash, and
password type retained. The final sampled X11 CLIPBOARD and PRIMARY retained
their original markers and contained neither the old nor new synthetic secret.
These are final sampled clipboard observations, not proof that every transient
owner state was inspected. The runtime adversarial suite separately qualifies
selection-related clipboard behavior.

The screenshot visibly shows the masked password, unchanged Reference and
“Entry received. Not submitted.” It does not prove the password bytes; the
independent app hash does. Its SHA-256 is
`ca9b9f6657b0d8f1b5d30cb6e9cd06e0955006855d77320b728aadc1b9e05dcd`.
The original automated report remains `passed:false` because it requires a
separate visual review; `workflow_oracle_passed:true` records the independent
checks. The subsequent visual review is a separate hash-bound record. There was
no agent rerun or promotion of image availability into a verified receipt.

## Cost and limits

The attempt took 97.385 seconds, including model/CLI time. Reported backend time
summed to 1,750 ms. It used five tool calls, one 71,001-byte screenshot and no tool
errors. Codex CLI was 0.155.1; the resolved model was not exposed in its JSON.
Usage reported 158,327 input tokens (131,840 cached; 26,487 uncached), 419 output
tokens and zero separately reported reasoning tokens. These are CLI-reported
counts, not inferred image-token costs.

There was no observed capability-selection friction. The agent's final statement
that it replaced the requested string relies on dispatch plus a content-free UI
receipt; it cannot independently verify secret exactness through public readback.
The app hash establishes exactness only for this test. Likewise, “the page is
open” was true at the final screenshot; the explicitly temporary owned browser
was deleted when the evaluator ended its MCP connection. This is not durable
browser state after a Codex task ends.

This used sandboxed Chromium 153.0.8010.12/Playwright 1.63.0 on private Xvfb/XFWM,
with desktop and MCP UID 1001. The agent reused existing root CLI authentication
without reading or changing auth files. The root agent's read-only instruction
and trace grading are not adversarial filesystem isolation. The form has no
account or network service beyond loopback. Its application observer writes only
hashes/counters, while the intentionally retained client trace/prompt contains
the synthetic password argument; runtime response privacy does not erase client
prompt history. Never substitute real credentials into this evaluator.

Known owned evaluator/MCP/guardian/worker/Playwright/crashpad processes were absent
after completion and the recorded owned profile was removed. No global cleanup
or shared desktop mutation was performed.

## Reproduction and retained evidence

Run `uv sync --locked --no-default-groups --extra browser` in a dedicated checkout,
with the documented test Chromium installed, then (as root, using existing CLI
auth) `./.venv/bin/python scripts/agent_secret_eval.py`. The fixture uses the
repository's test-browser path; there is no runtime download. Coordinate ordinary
account process-proof tests before launching. The evaluator deliberately returns
nonzero pending separate visual review; never rerun simply to get a green result.

[Retained first attempt](../tests/evidence/agent-owned-secret-first-attempt/README.md)
contains the original result/events/logs, final image and separate review. The
public-MCP fixture preflight passed all six oracle checks before the agent ran.
An earlier preflight stopped on a Python argument-name collision before secret
entry; its original log is retained and is not counted as an agent attempt.
Four deterministic evaluator tests cover wrong hash/duplicate input, submit,
missing clipboard evidence and the distinction between dispatch and app proof.
