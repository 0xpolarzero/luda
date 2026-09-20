# Fresh-agent locale-form usability

On 2026-09-20, one fresh Codex agent completed the held-out locale-form task on its first attempt in **85.282 seconds**, within a 120-second budget. It used the installed Luda skill and public desktop MCP tools only. No failed attempt was discarded, no unchanged-code retry was run, and the agent received no steering after launch.

The task requested **18.11.2027 16:45 Europe/Berlin**, amount **12,35**, explicit selection of **Bergen, Norway** from autocomplete, and exactly one submission. The independent application file confirmed:

- Committed UTC time `2027-11-18T15:45:00+00:00`.
- Numeric value `12.35` and displayed text `12,35`.
- `Bergen, Norway` selected by the actual completion `match-selected` callback, once.
- Exactly one submitted and accepted form, with visible result `Accepted`.

There were 31 desktop tool calls and no server-reported tool errors. Their reported execution time totaled 4.468 seconds. The trace contains one installed-skill read, no other shell commands, no application-source or hidden-file reads, no direct file edits, no application launches and no network browsing by the agent. It checked the final visible result and left the application open.

## Affordances that caused extra work

Autocomplete consumed most of the exploratory calls. Semantic text replacement, explicit focus and Down did not expose suggestions. The agent inspected again, restored entry focus, selected its text and tried GUI paste; the popup still was not visible. Two native BackSpace presses finally exposed an observed popup. The agent then used the ordinary `desktop_click` tool to select the intended third row. It did not need a separate popup API, and the independent callback proved this was selection rather than literal insertion. These are observations of this fixture, not a general claim about what always opens GTK completion.

The agent initially set the numeric field through text replacement. Exact text readback was `12,35`, but inspection still showed provider Value `10.0`. Before submitting, it used `desktop_set_value(12.35)`. Text verification had been correct; the field had not yet committed its numeric value. This is a useful distinction, but the skill could make the preferred Value-interface workflow clearer.

The evidence supports clarifying that verified text does not imply focus, numeric commitment, suggestion selection or submission success. Prefer the Value interface for numeric controls that expose it; observe completion UI explicitly before selecting a suggestion. No new API or runtime behavior was introduced for this evaluation.

## Environment and retained evidence

The backend and copied installed skill came from immutable revision `d9be0222e971a9d81234a53b624ff54a5be9e7b1`. The source fingerprint was unchanged before/after: `3d5fe191317342d950221c4e71160c888b20a4274a0ed53eef7c236ae19e24e9`.

Codex CLI was **0.155.1**, using existing authentication and its default model. The JSON events did not identify the resolved model; none is inferred. CLI usage reported 507,863 cumulative input tokens, 461,824 cached input tokens and 1,597 output tokens, including 58 reasoning output tokens. These are cumulative turn usage, not a unique prompt size.

The CLI ran as uid 0 because its installed executable and existing authentication belong to root. A root-only CLI did not prevent an ordinary-user desktop test: a controlled `runuser` MCP command ran Luda as uid **1001**, confirmed by `desktop_doctor`, and the GTK fixture, private Xvfb, D-Bus and locale environment also ran as uid 1001. No authentication file was inspected or copied, and no existing CLI configuration was changed. This does not qualify ordinary-user Codex authentication or fresh Mac/SSH onboarding.

Full JSON tool events, screenshots, stderr, prompt, oracle and source hashes are retained under `artifacts/agent-locale/run-1789871033598290361/` in the evaluation checkout `/workspace/luda-agent-data-eval` and copied to the main checkout. Private-desktop cleanup left no process carrying the run's unique temporary paths. One successful local trial is not a statistical reliability claim.

`scripts/agent_locale_eval.py` reproduces the bounded evaluation with an explicit immutable `--backend-root`, existing root Codex authentication, an ordinary `--desktop-user`, and installed or extracted locale sources through `--locale-source`. It copies the backend's installed skill into an otherwise empty agent workspace and grades the independent fixture oracle after the run.
