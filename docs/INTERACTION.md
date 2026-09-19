# Window and pointer interaction

`InteractionMixin` is composed with `Desktop`; public tool callers must hold its transaction lock. Window identities and screenshot expiry retain Desktop's contract.

`manage_window(window_id, action, ...)` accepts move (`x,y`, outer frame origin), resize (`width,height`, client dimensions), maximize, minimize, restore, close, or workspace (`workspace`). It rejects irrelevant parameters before dispatch. Window-manager state is polled for 1.5 seconds; verified means the requested WM state was observed, not that application content was saved. Close sends the normal close request and never kills a process or confirms an unsaved-data dialog. Window managers may constrain geometry; such requests return dispatched if the exact state is not observed.

`workspaces()` and `switch_workspace(workspace)` use existing workspace indexes. Creation/deletion is deliberately outside this contract.

`hover` uses screenshot image pixels. `drag_between` accepts source and destination window identities with a single fresh screenshot. The source must be active; the destination must be present at its observed bounds. Pointer operations validate both endpoints before button-down and always attempt button release after a failure. A dispatched drag does not prove that an application accepted a drop. Occlusion, human interference and application drag semantics need post-action observation.

## Evidence

On the Silo Ubuntu 24.04 ARM64 XFCE/KasmVNC guest, `tests/live_interaction.py` verified move, resize, maximize, restore, minimize, restore and close against the WM's observed state; hover against independent `xdotool getmouselocation` output. `tests/live_popup.py` created an actual GTK override-redirect popup and verified its transient owner and exact 100×80 client dimensions. Both tests hold the shared desktop lease for their entire process lifetime and terminate only their own fixtures.

`tests/test_interaction.py` covers malformed arguments with zero dispatch, finite coordinate validation, screenshot scale and half-open bounds, stale/missing observations, changed layout/resolution, destination prevalidation, input release after failure, release failure preserving the initial error, and unverified state reporting.

Popup descriptors are observation-only. They do not by themselves authorize actions: menus without an owner hint, XID reuse, occlusion, nested popups and application-specific menu interaction remain separate qualification work. Direct Xlib reads assume a responsive local display; process isolation is needed to enforce deadlines against a completely stalled X server.
