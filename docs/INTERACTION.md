# Window and pointer interaction

`InteractionMixin` is composed with `Desktop`; public tool callers must hold its transaction lock. Window identities and screenshot expiry retain Desktop's contract.

`manage_window(window_id, action, ...)` accepts move (`x,y`, outer frame origin), resize (`width,height`, client dimensions), maximize, minimize, restore, close, or workspace (`workspace`). It rejects irrelevant parameters before dispatch. Window-manager state is polled for 1.5 seconds; verified means the requested WM state was observed, not that application content was saved. Close sends the normal close request and never kills a process or confirms an unsaved-data dialog. Window managers may constrain geometry; such requests return dispatched if the exact state is not observed.

`workspaces()` and `switch_workspace(workspace)` use existing workspace indexes. Creation/deletion is deliberately outside this contract.

`hover` uses screenshot image pixels. `drag_between` accepts source and destination window identities with a single fresh screenshot. The source must be active; the destination must be present at its observed bounds. Pointer operations validate both endpoints before button-down and always attempt button release after a failure. A dispatched drag does not prove that an application accepted a drop. Occlusion, human interference and application drag semantics need post-action observation.

## Evidence

On the Silo Ubuntu 24.04 ARM64 XFCE/KasmVNC guest, `tests/live_interaction.py` verified move, resize, maximize, restore, minimize, restore and close against the WM's observed state; hover against independent `xdotool getmouselocation` output. `tests/live_popup.py` created an actual GTK override-redirect popup and verified its transient owner and exact 100×80 client dimensions. Both tests hold the shared desktop lease for their entire process lifetime and terminate only their own fixtures.

`tests/test_interaction.py` covers malformed arguments with zero dispatch, finite coordinate validation, screenshot scale and half-open bounds, stale/missing observations, changed layout/resolution, destination prevalidation, input release after failure, release failure preserving the initial error, and unverified state reporting.

Popup descriptors are observation-only. They do not by themselves authorize actions: menus without an owner hint, XID reuse, occlusion, nested popups and application-specific menu interaction remain separate qualification work. All Xlib reads now run in an isolated helper with a two-second timeout and the operation-level deadline/cancellation policy. No native display handle survives a read.

`tests/live_drag.py` additionally passed an actual GTK drag-and-drop between two separately positioned windows: the destination's `drag-data-received` callback wrote the exact UTF-8 payload `luda drag payload 日本語` to an independent file. The tool correctly returned `dispatched`; the test, not the generic tool, verified the application transfer. This qualifies this GTK COPY fixture, not arbitrary file-manager or cross-toolkit transfers. Current-workspace assignment and switching were also verified; cross-workspace animation behavior remains unqualified.

## X11 fault isolation

The public `X11` object launches a fresh `luda._x11_helper` process for each read. Native ctypes calls live only in its private `_NativeX11` implementation. This contains fatal Xlib I/O errors and uses `common.run` to terminate stalled reads. There are no reconnect handles to reset: even the root-window property is fetched from a new connection. `close()` is idempotent and releases no persistent resources.

`tests/live_x11_isolation.py` uses its own disposable Xvfb, never the shared desktop: SIGSTOP produced a TIMEOUT after 2.002 seconds, SIGCONT restored reads, a terminated display reported DISPLAY_UNAVAILABLE, and the same wrapper read the new 800×600 geometry after restart. All three GTK interaction/popup/drag probes passed again with the isolated implementation. Seven helper unit tests cover crashes, malformed replies, cancellation, timeout, bad arguments and per-read process isolation.

The tradeoff is process startup for each metadata read. Window enumeration therefore scales with the number of windows; a batched helper query can reduce overhead without introducing a persistent Xlib connection. Errors from one helper call do not mark a future connection permanently unavailable.
