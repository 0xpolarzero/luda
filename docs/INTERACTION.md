# Window and pointer interaction

`InteractionMixin` is composed with `Desktop`; public tool callers must hold its transaction lock. Window identities and screenshot expiry retain Desktop's contract.

`manage_window(window_id, action, ...)` accepts move (`x,y`, outer frame origin), resize (`width,height`, client dimensions), maximize, minimize, fullscreen, raise, restore, close, or workspace (`workspace`). It rejects irrelevant parameters before dispatch. Window-manager state is polled for 1.5 seconds; verified means the requested WM state was observed, not that application content was saved. Close sends the normal close request and never kills a process or confirms an unsaved-data dialog. Window managers may constrain geometry; such requests return dispatched if the exact state is not observed.

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

## Real X resource generations

`X11.window_tokens(xids)` returns a batch dictionary from XID to a 128-bit generation nonce encoded as 32 lowercase hexadecimal characters. It initializes `_LUDA_WINDOW_TOKEN` on the actual X resource using the standard STRING type and 8-bit format. The root should include this generation in managed-window identities and popup signatures. A normal move, hide, or remap retains the property. Actual resource destruction removes it, so even the same process recreating the same numeric XID receives a new generation.

Concurrent initialization uses a brief XGrabServer around reading, validating and creating the properties. Entropy is generated before the grab. All preexisting tokens in the batch are validated before creating missing ones. Malformed type, format, length, bytes or oversized property data produce INVALID_WINDOW_TOKEN and are never accepted or overwritten. Disappeared resources are omitted. The normal finally path releases and flushes the grab; killing a timed-out helper closes its X connection and the X server releases the grab itself. The entire helper remains subject to the two-second subprocess/operation bound. Metadata initialization changes only this private property, not application content or user input.

`tests/live_window_tokens.py` used checked XCB requests against a disposable Xvfb to destroy and recreate the **same numeric XID on the same client connection**. It verified a different generation, identical results from racing independent initializers, preservation through move/unmap/remap, rejection of a malformed preexisting property, release after that exception, and release after killing a helper which demonstrably held a processed server grab. Decoder tests also cover wrong types, lengths, remaining bytes, uppercase/non-hex/NUL/non-ASCII values and invalid batch arguments.

This is resource-lifetime identity, not protection from hostile X clients. Other clients can delete or forge a valid property; deleting it intentionally invalidates previously recorded identity. The nonce does not imply unchanged application content, widget content, or menu contents. Unmapping and remapping the same still-living resource intentionally retains its identity. A server grab briefly stalls other X clients; batches are capped at 512 and connection death releases the lock, but desktop responsiveness during enormous batches still needs workload measurement.

## Fullscreen, raise and blocked close

`desktop_window(..., action="fullscreen")` requests the EWMH fullscreen state and verifies the actual `_NET_WM_STATE_FULLSCREEN` flag. `restore` now removes fullscreen as well as maximization and minimization. The window manager determines monitor coverage and constrained geometry.

`action="raise"` raises a visible window above peers with the same declared layer flags without requesting activation. It verifies actual root-child stacking and unchanged active window. Already-topmost windows need no mutation. Sticky windows include peers from the active workspace. Hidden windows are rejected. Focus changes caused by another actor during the operation produce FOCUS_CHANGED with uncertain effect; the tool never attempts to counteract human focus changes.

On XFWM, a raw XRaiseWindow with no sibling activates the client, frame stacking requests are ignored, and `_NET_RESTACK_WINDOW` is unsupported. The isolated helper instead sends a ConfigureRequest with an explicit highest peer sibling, preserving window-manager layer handling without an activation request. [XFWM's request handling](https://github.com/xfce-mirror/xfwm4/blob/master/src/client.c) explains this distinction. Other window managers may decline the request; verification then remains dispatched.

Close now reports `outcome="closed"` when the owner disappears, `blocked_by_dialog` with observed modal window IDs when the owner remains with a linked modal dialog, or `still_open` when no completion is observed. The dialog case remains dispatched, never pretends the application closed, and never confirms a dialog or infers its contents.

The extended live interaction fixture verified fullscreen entry/exit through independent xprop reads; raise and repeated raise through independent xwininfo stacking and xdotool focus reads; preservation below an owned above-layer fixture; and a synthetic unsaved-close dialog whose independent oracle confirmed it was left unanswered. Nine unit cases cover malformed state arguments, hidden and sticky raises, explicit-sibling dispatch, focus-change refusal, idempotency, fullscreen restoration and blocked close.

Cross-window drags now use the same `held_button` companion as same-window drags. Normal errors/cancellation release through the context manager; controller death closes the watchdog pipe and triggers independent bounded release. Unit tests mock the guard, verify cleanup delegation on motion failure and prevent real input during test execution. The actual two-window GTK UTF-8 drop oracle passed after integration.
