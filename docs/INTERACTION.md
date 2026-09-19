# Window and pointer interaction

`InteractionMixin` is composed with `Desktop`; public tool callers must hold its transaction lock. Window identities and screenshot expiry retain Desktop's contract.

`manage_window(window_id, action, ...)` accepts move (`x,y`, outer frame origin), resize (`width,height`, client dimensions), maximize, minimize, restore, close, or workspace (`workspace`). It rejects irrelevant parameters before dispatch. Window-manager state is polled for 1.5 seconds; verified means the requested WM state was observed, not that application content was saved. Close sends the normal close request and never kills a process or confirms an unsaved-data dialog. Window managers may constrain geometry; such requests return dispatched if the exact state is not observed.

`workspaces()` and `switch_workspace(workspace)` use existing workspace indexes. Creation/deletion is deliberately outside this contract.

`hover` uses screenshot image pixels. `drag_between` accepts source and destination window identities with a single fresh screenshot. The source must be active; the destination must be present at its observed bounds. Pointer operations validate both endpoints before button-down and always attempt button release after a failure. A dispatched drag does not prove that an application accepted a drop. Occlusion, human interference and application drag semantics need post-action observation.

## Evidence

On the Silo Ubuntu 24.04 ARM64 XFCE/KasmVNC guest, `tests/live_interaction.py` verified move, resize, maximize, restore, minimize, restore and close against the WM's observed state; hover against independent `xdotool getmouselocation` output. `tests/live_popup.py` created an actual GTK override-redirect popup and verified its transient owner and exact 100×80 client dimensions. Both tests hold the shared desktop lease for their entire process lifetime and terminate only their own fixtures.

`tests/test_interaction.py` covers malformed arguments with zero dispatch, finite coordinate validation, screenshot scale and half-open bounds, stale/missing observations, changed layout/resolution, destination prevalidation, input release after failure, release failure preserving the initial error, and unverified state reporting.

Raw X11 popup descriptors are observation-only. The interaction layer now grants snapshot-scoped tokens only after verifying a transient-owner chain and matching process identity. Menus without an owner hint remain unsupported; same-process XID remapping between observations cannot be detected without an event history. All Xlib reads now run in an isolated helper with a two-second timeout and the operation-level deadline/cancellation policy. No native display handle survives a read.

`tests/live_drag.py` additionally passed an actual GTK drag-and-drop between two separately positioned windows: the destination's `drag-data-received` callback wrote the exact UTF-8 payload `luda drag payload 日本語` to an independent file. The tool correctly returned `dispatched`; the test, not the generic tool, verified the application transfer. This qualifies this GTK COPY fixture, not arbitrary file-manager or cross-toolkit transfers. Current-workspace assignment and switching were also verified; cross-workspace animation behavior remains unqualified.

## X11 fault isolation

The public `X11` object launches a fresh `luda._x11_helper` process for each read. Native ctypes calls live only in its private `_NativeX11` implementation. This contains fatal Xlib I/O errors and uses `common.run` to terminate stalled reads. There are no reconnect handles to reset: even the root-window property is fetched from a new connection. `close()` is idempotent and releases no persistent resources.

`tests/live_x11_isolation.py` uses its own disposable Xvfb, never the shared desktop: SIGSTOP produced a TIMEOUT after 2.002 seconds, SIGCONT restored reads, a terminated display reported DISPLAY_UNAVAILABLE, and the same wrapper read the new 800×600 geometry after restart. All three GTK interaction/popup/drag probes passed again with the isolated implementation. Seven helper unit tests cover crashes, malformed replies, cancellation, timeout, bad arguments and per-read process isolation.

The tradeoff is process startup for each metadata read. Window enumeration therefore scales with the number of windows; a batched helper query can reduce overhead without introducing a persistent Xlib connection. Errors from one helper call do not mark a future connection permanently unavailable.

## Context menus and submenus

`observe_popups(windows=None)` resolves each mapped override-redirect popup through its `WM_TRANSIENT_FOR` chain (maximum 16 links) to a currently listed managed owner window. Every popup in the chain must have the same `_NET_WM_PID`; `/proc` process start must match the owner's identity. Missing owners, missing or conflicting PIDs, cycles and dead processes are excluded. Matching the application's PID alone never establishes which window owns a menu.

Returned descriptors include an opaque `popup_id`, owner window token, PID/start, XID, transient owner and bounds. `popup_signature(popups)` ignores ephemeral tokens but includes geometry and owner identity in stacking order. Integrators capture before and after screenshots, compare signatures, and store the final descriptors in `snapshots[snapshot_id]['popups']`; expose the descriptors alongside screenshot windows.

`pointer_popup(owner_window_id, popup_id, snapshot_id, x, y, kind='click', button='left', count=1, direction='down')` supports click, hover and scroll. It requires the token in that snapshot, active owner identity, unchanged managed-window layout and popup signature, unchanged resolution, and coordinates inside the popup. An isolated native hit test also requires the popup to be the topmost root surface at that point. Parent client bounds do not restrict an authorized popup, allowing context menus and submenus outside the parent. Each mutation remains dispatched until the caller verifies an application result.

The actual `tests/live_menu.py` GTK fixture opened a menu outside its owner's bounds, hovered its parent item, opened a submenu, and clicked its command. The callback independently wrote exact UTF-8 proof. The same test rejected pre-cancelled input, an unrelated unowned popup overlay covering the submenu, and reuse of a vanished popup observation. Eleven unit cases cover ownership chains, ambiguous/cyclic links, conflicting and dead/reused process identities, forged tokens, bounds, expiry, geometry changes and zero-dispatch rejection.

These checks are conservative, not an adversarial security boundary. Other X11 clients can manipulate desktop properties/input. A popup that unmaps and remaps with identical XID, owner and geometry entirely between observations cannot be distinguished without a continuous event history. Applications omitting owner/PID hints require another verified targeting mechanism; the tool does not guess. There remains an unavoidable race between checking a surface and dispatching input if another client or human changes the desktop.

`X11.geometries([xid,...])` batches up to 512 geometry reads in one isolated helper, returning an integer-keyed dictionary and omitting disappeared windows. In a four-window live sample, separate reads took 69.95 ms versus 16.91 ms batched with identical geometry. This does not keep a persistent native connection.
