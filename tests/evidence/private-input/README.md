# Independent input validation

2026-09-20. Private Xvfb, XFWM, GTK3 fixtures; no shared desktop touched.
Runtime includes commits `967456c`, `618a464`, and `6d4d1cb`.

Commands from an installed, independent worktree venv:

```
.venv/bin/python tests/live_private_input.py
.venv/bin/python tests/live_private_input_owner.py
```

`mcp.json` records nine passing real MCP cases. Independent GTK application
processes write observed text/counters to files. A separate human X connection
holds keys/buttons and types while the agent acts. Human raw keyboard focus is
sampled every 5 ms; pointer position and held state are checked before and after
each action. Click feedback is verified in actual captured desktop pixels.

Cases include click, hover, wheel ticks, typing, held human Shift, held human
mouse button, drag, concurrent exact text in two applications, popup interaction
while human typing remains usable, and rejection of a stale screenshot. The
same original six-case fixture run against the previous shared-input runtime
failed: human focus/pointer moved, held human input blocked agent actions, and
popup input interfered with human typing. This establishes that the assertions
distinguish the change from its predecessor.

`owner.json` records independent lifecycle checks: pointer/key separation,
same-key release isolation, normal cleanup, and owner SIGKILL cleanup.

These are bounded application/device checks, not qualification of every Linux
application, toolkit, window manager, viewer, or browser. Five-millisecond focus
sampling cannot prove the absence of a shorter transition. Browser behavior and
legacy core-only applications require separate evidence.

`cleanup.json` records the private-pair disappearance regression check. With
matching human Control and pointer-button input held, keyboard and pointer release
helpers prove old ownership ended without emitting releases. The old injector’s
nonce-owned X resource is independently confirmed destroyed before cleanup is
acknowledged. A different generation is checked before private binding or client
disconnection. This last case supplies a different generation; it is not itself
a full X-server restart test.
