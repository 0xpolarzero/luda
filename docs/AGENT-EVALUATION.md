# Fresh-agent usability probe

`scripts/agent_eval.py` starts a new authenticated Codex CLI process with Luda MCP tools and a discoverable `.agents/skills/luda` in an otherwise empty temporary workspace. The agent receives a delivery-preferences task, not a sequence of tool calls or application source. A separate GTK process records committed values for the harness's independent oracle.

The first completed task passed: exact Unicode/emoji/LF/Tab/trailing-newline text, enabled updates, Express delivery, save, and visible saved-status verification. The fresh agent used the installed skill and public desktop tools. Runtime was 27.386 seconds in this local test. This is one synthetic task; it does not establish general usability, repeatability or Mac SSH onboarding.

Two harness failures are retained as findings: direct MCP startup did not inherit DISPLAY/session D-Bus until explicit env forwarding was added; then read-only Codex policy blocked mutations until the isolated task's Luda tools were explicitly preauthorized. The installed guest configuration uses `luda-session` to discover its XFCE session; direct fresh-Xvfb tests instead forward their explicit test environment. No global agent configuration is changed.

The CLI run uses `--ephemeral`, `--ignore-user-config`, a read-only command sandbox, and per-run Luda tool approval. Its synthetic result/transcript remain under ignored `artifacts/agent-eval`. It requires an already authenticated Codex CLI and can consume model usage; this is an explicit development evaluation, not a Luda runtime dependency or default CI job.

See official [non-interactive execution](https://learn.chatgpt.com/docs/non-interactive-mode) and [MCP configuration](https://learn.chatgpt.com/docs/extend/mcp?surface=cli). The local CLI under test was 0.155.1. MCP approval behavior and remote placement should be tested against the actual host/client version.

Run on a fresh Xvfb display with XFWM4 and a private session D-Bus, setting `LUDA_ISOLATED_TEST_DISPLAY=1`. Then execute `.venv/bin/python scripts/agent_eval.py`. The script refuses ordinary display execution without that explicit isolated-test opt-in. It never reads or provisions authentication credentials.

## Three-task expansion (2026-09-20)

The expanded harness at commit `eb76093` ran three fresh, ephemeral Codex processes against unchanged code in a separate worktree and virtual environment. Each process received only its task, the installed skill, and public MCP tools. The tasks were not expressed as tool sequences. Synthetic oracle files were outside the agent workspace; the harness inspected them after the agent finished.

| Task | Independent result | Time | Completed desktop calls |
| --- | --- | ---: | ---: |
| Delivery preferences form | Exact committed Unicode/LF/Tab/emoji/final-newline text and both requested options | 33.228 s | 12 |
| Real Mousepad Save As | Exact UTF-8 bytes saved under the requested Unicode filename through the graphical dialog | 60.180 s | 16 |
| Drawn palette/grid board | Committed `{color: Amber, cell: B2, saved: true}` | 49.724 s | 13 |

The board exposes no semantic child controls. The fresh agent inspected the sparse accessibility tree, then used screenshots and pointer actions to open the drawn palette, select Amber, mark B2 and commit. Mousepad required the actual Save As dialog and a Save-button activation after entering the absolute path. Both tasks ended with visible-result verification; the harness separately checked the persisted state. The harness itself did not execute the task's GUI actions.

Trace grading passed for all three: commands were limited to reading the installed skill, MCP calls used public `luda.desktop_*` tools, and there were no direct file-change operations. The read-only command sandbox does not itself prohibit all filesystem reads: the trace audit is therefore a separate qualification condition, not a security boundary. Both started and completed commands are audited so an interrupted forbidden command cannot disappear from the grade. Five deterministic tests cover these rules.

Each task was bounded to 150 seconds. Source hashes before and after were identical: `5e280384046c6782c85cf4dbbd96c1e8e4a0e0651cb278c1f19fb5f42c91b374`. Per-task artifacts record the exact non-secret argv, CLI and package versions, task prompt, usage, oracle grade, trace, and file-level source hashes. Artifacts remain ignored because they contain synthetic screen contents and task text.

Returned usage (input totals include cached input):

| Task | Input tokens | Cached input | Output tokens |
| --- | ---: | ---: | ---: |
| Form | 127,193 | 111,872 | 630 |
| Mousepad | 416,529 | 369,792 | 945 |
| Canvas | 179,804 | 149,760 | 832 |

Environment: ARM64 Linux; Python 3.12.3; Codex CLI 0.155.1; MCP SDK 1.30.0; GTK 3.24.41; AT-SPI 2.52.0; Mousepad 0.6.1; XFWM4 4.18.0; Xvfb 21.1.12. These authenticated CLI runs used UID 0 on a private test display; they do not qualify desktop-user permission boundaries or remote SSH setup. The CLI default model was used. Its resolved model identity is **unknown** because the JSON event stream does not expose it; this limits reproducibility. No model identity was inferred from authentication or service details.

The first canvas launch failed before an agent ran because system Cairo Python bindings were absent. That harness failure was retained in `initial-result.json`; installing `python3-cairo` and `python3-gi-cairo` allowed the fixture to run unchanged. They are evaluation-fixture dependencies, not new Luda runtime requirements. The canvas was then run alone on another fresh private display. Form and Mousepad were not rerun to obtain favorable outcomes.

To run all three, with the listed GUI dependencies and an already authenticated CLI:

```sh
LUDA_ISOLATED_TEST_DISPLAY=1 xvfb-run -a \
  -s '-screen 0 1440x900x24 -nolisten tcp' \
  dbus-run-session -- .venv/bin/python scripts/agent_eval.py
```

The harness starts and stops its own XFWM4 and app processes. Use `--tasks form mousepad canvas` to select tasks; `--timeout` cannot exceed 150 seconds per agent. It changes neither global Codex configuration nor the existing desktop session. The installed skill is copied into each empty task workspace, and `--ignore-user-config --ephemeral --sandbox read-only` prevents loading persistent conversational state or user configuration.

These are three successful local runs across different interaction styles, not a statistically meaningful success rate. They do not establish repeatability, unseen-application generalization, adversarial-document resilience, accessibility support for every toolkit, or Mac-to-guest onboarding quality. Large cumulative input usage also shows that task completion alone is insufficient to establish efficiency.
