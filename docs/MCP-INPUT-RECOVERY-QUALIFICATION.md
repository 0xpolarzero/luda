# Public input recovery qualification

`tests/live_mcp_input_recovery.py` uses the actual stdio MCP server and public `desktop_recover_input`, status, control, window, activation and keyboard tools. It does not substitute server methods or fake recovery metadata. An independent native X keymap/pointer oracle and a passive GTK text fixture check effects.

Run as an ordinary user with locked dependencies:

```sh
.venv/bin/python scripts/qualification_matrix.py --suites mcp-input-recovery
```

The matrix supplies private XDG directories and D-Bus. The test creates a separate owned Xvfb so it can deliberately stop and replace that server without affecting the caller's desktop. It discovers only descendants of its own MCP process, records their process start identities before stopping them, resumes only matching identities during cleanup, and closes its owned apps. The outer matrix watchdog also cleans tagged descendants.

The local X11 run passed 15 checks:

- The recovery tool is discoverable over MCP.
- After the independent oracle observes Control pressed, the test stops the real injector, guardian and X server, then pauses through MCP. The key operation reports `KEYBOARD_CLEANUP_PENDING` with uncertain effect. The recovery watcher resumes the guardian, kills the stopped injector, and retains quarantine when the blocked X server prevents cleanup.
- Further keyboard input gets `BUSY`. Public recovery while X remains stopped returns a bounded timeout with the ownership record still pending.
- Resuming the original X server permits public recovery to verify owned-key release. The independent keymap is empty. Pause remains set, new input gets `CONTROL_PAUSED`, and only an explicit resume allows a new character to reach the GTK fixture.
- After a second real failure, the test replaces its X server at exactly the same display and authority path. It holds a matching Control key and mouse button on the replacement. Public recovery recognizes the changed generation, skips cleanup input, clears only the old quarantine, and preserves those held inputs and the paused state.

Evidence is written under `artifacts/mcp-input-recovery` and copied into the immutable per-run matrix directory with source fingerprints and process-cleanup outcome. The first complete run took approximately 15 seconds, with no tagged survivors.

This qualifies the tested Xvfb lifecycle, not arbitrary remote X proxies, Wayland, a hostile client modifying Luda's root properties, or separation of concurrent human presses of the exact same key on one unchanged server. A same-server client-resource reuse review is separate from server-generation replacement.
