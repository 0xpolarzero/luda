# First-attempt soft-line-break usability evidence

> Historical record from before Editor Bridge became a separate add-on. Tool names, source paths and test commands below describe the recorded revision, not the current core installation. For current setup and supported behavior, see [Editor Bridge](../addons/editor-bridge/README.md).

One fresh Codex CLI attempt completed the requested rich edit and saved the correct model, but **failed the original strict instruction-compliance rubric**. Its initial `list_mcp_resources` call was read-only discovery outside the requested `desktop_*` tool set. This is not reclassified as a strict pass. No second attempt or prompt tuning followed.

The held-out task asked for three specified lines within the same paragraph, like Shift+Enter, replacing only the middle of a note while preserving its bold prefix and italic suffix. It named neither `line_breaks="hard_break"` nor a tool sequence. The agent read the installed skill, observed the editor, selected code-point offsets 8..27 and chose clipboard insertion with `hard_break` on its first typing call. It then unnecessarily selected the new text and dispatched Ctrl+B to remove inherited bold. This fixture has no toggle-bold shortcut binding; readback showed the text still bold, which the final answer correctly disclosed. The task did not prescribe the replacement's formatting.

The independent save-button oracle establishes exact Unicode text, one paragraph containing two `hard_break` nodes, the original prefix/suffix marks, and selection head at code-point 49 after the insertion. The final selection remains a range (ProseMirror anchor 10/head 51), not a collapsed caret. Three trusted paste events were recorded. The final screenshot shows the saved status and three lines; pixels alone do not prove exact Unicode or the underlying paragraph structure. The agent disclosed the final clipboard payload and that the previous clipboard contents were not restored.

There were 16 MCP calls: initial resource discovery, then 15 desktop calls: doctor, open browser, inspect, read, focus, select, type, select, press keys, read, inspect twice, invoke Save, inspect Saved, observe. There were no tool errors, direct file edits or injected hidden application actions. The only shell command read the installed skill. This is evidence of this workflow's discoverability with one agent, not a population success rate or universal editor support.

The attempt lasted 84.923 seconds under a 300-second budget, using Codex CLI 0.155.1 and Chromium 153.0.8010.12. The resolved model identity was not exposed in retained JSON and is not guessed. The CLI used existing root authentication; desktop, browser and MCP ran as UID 1001 on private Xvfb/D-Bus with private XDG directories. No credentials are retained. The source fingerprint stayed `bf32a9b6a77cd5af45e28efd28e5ddf634ae62b6a067efa81200aecde49370cb` throughout, based on main `aef930b` plus the new harness/fixture. A subsequent harness import-isolation correction and documentation were unit-tested; the paid attempt was not rerun.

Original trace, result, logs, exact saved model and screenshot are retained in [the evidence directory](../tests/evidence/agent-hard-break-first-attempt/README.md). Runtime and skill were unchanged. Run a separately authorized new evaluation with:

```sh
uv sync --frozen --extra browser
.venv/bin/python scripts/agent_hard_break_eval.py --executable /absolute/trusted/chrome --timeout 300
```

This command consumes an actual authenticated agent attempt. Unit tests do not launch agents: `PYTHONPATH=tests .venv/bin/python -m unittest test_agent_hard_break_eval test_agent_rich_eval test_agent_eval` (15 passed).

A subsequent bounded usability change makes clipboard success receipts repeat the native route's verification scope: unaffected marks are preserved, new formatting follows application behavior, and saving remains separate. Skill guidance starts directly with doctor and discourages unrequested formatting changes or assumed shortcut bindings. No formatting API or input behavior changed. Focused response and exact Linux skill-mirror tests cover the changes; the original attempt and strict rubric failure remain unchanged, and no improved agent success rate is claimed.
