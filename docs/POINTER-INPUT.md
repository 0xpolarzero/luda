# Supervised click and wheel input

`pointer_input.click_button(button, count=1, target=None)` supports X11 buttons 1–7 and 1–20 repeats. The caller validates and positions the pointer and supplies the active owner XID. Native preflight refuses already held keys/buttons or latched keyboard state without releasing them. Caps/Num locks are preserved.

A companion owns the injection process. Cancellation or controller death stops and reaps that process, disconnects its nonce-identified X connection, then releases only the planned button. Injection and cleanup are bound to the original X-server generation. Restarting a server at the same display name cannot cause old cleanup to release input on its replacement. Incomplete cleanup blocks further input through the shared recovery registry; explicit input recovery uses each record's original environment and never replays clicks or wheel events.

Successful dispatch is not proof of an application action. Inspect the resulting UI. Concurrent human input can move the pointer or press the same planned button; X11 cannot attribute that shared button state. Preflight is a point-in-time check. This helper does not cover the separate held-drag watchdog.

`tests/live_pointer_guard.py` creates its own Xvfb, D-Bus session, private XDG directories, XFWM and GTK fixture. Independent application-file and XQueryPointer oracles verify triple clicks, vertical/horizontal wheel counts, refusal with an already held button, controller SIGKILL after a stopped injector has pressed a button, and cancellation mid-scroll without later events. This is synthetic native qualification, not universal application compatibility.
