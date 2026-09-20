# Fresh-agent usability probe

`scripts/agent_eval.py` starts a new authenticated Codex CLI process with Luda MCP tools and a discoverable `.agents/skills/luda` in an otherwise empty temporary workspace. The agent receives a delivery-preferences task, not a sequence of tool calls or application source. A separate GTK process records committed values for the harness's independent oracle.

The first completed task passed: exact Unicode/emoji/LF/Tab/trailing-newline text, enabled updates, Express delivery, save, and visible saved-status verification. The fresh agent used the installed skill and public desktop tools. Runtime was 27.386 seconds in this local test. This is one synthetic task; it does not establish general usability, repeatability or Mac SSH onboarding.

Two harness failures are retained as findings: direct MCP startup did not inherit DISPLAY/session D-Bus until explicit env forwarding was added; then read-only Codex policy blocked mutations until the isolated task's Luda tools were explicitly preauthorized. The installed guest configuration uses `luda-session` to discover its XFCE session; direct fresh-Xvfb tests instead forward their explicit test environment. No global agent configuration is changed.

The CLI run uses `--ephemeral`, `--ignore-user-config`, a read-only command sandbox, and per-run Luda tool approval. Its synthetic result/transcript remain under ignored `artifacts/agent-eval`. It requires an already authenticated Codex CLI and can consume model usage; this is an explicit development evaluation, not a Luda runtime dependency or default CI job.

See official [non-interactive execution](https://learn.chatgpt.com/docs/non-interactive-mode) and [MCP configuration](https://learn.chatgpt.com/docs/extend/mcp?surface=cli). The local CLI under test was 0.155.1. MCP approval behavior and remote placement should be tested against the actual host/client version.

Run on a fresh Xvfb display with XFWM4 and a private session D-Bus, setting `LUDA_ISOLATED_TEST_DISPLAY=1`. Then execute `.venv/bin/python scripts/agent_eval.py`. The script refuses ordinary display execution without that explicit isolated-test opt-in. It never reads or provisions authentication credentials.
