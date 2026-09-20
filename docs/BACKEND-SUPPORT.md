# Explicit X11 backend boundary

Luda currently supports the selected native X11 desktop. Native Wayland and
Xwayland are rejected with `UNSUPPORTED_BACKEND`, effect `none`, before normal
MCP observation or input handlers. Doctor remains available and reports
`ready: false` plus `display_error_code`; status, pause and owned-input recovery
remain available. Application catalog discovery remains a filesystem operation.
No session is started, switched, unlocked or converted.

The native metadata helper queries the actual server's `XWAYLAND` extension on
every new connection. [The X.Org protocol specification](https://sources.debian.org/src/xorgproto/2024.1-1/xwaylandproto.txt/)
defines this as an explicit Xwayland identification mechanism. This works without
Wayland environment hints. When DISPLAY is absent and WAYLAND_DISPLAY or
XDG_SESSION_TYPE declares Wayland, refusal occurs before opening Xlib. With no
display and no Wayland hint, the error remains DISPLAY_UNAVAILABLE; no default
`:0` display is guessed. An explicitly selected native X11 server is not rejected
merely because unrelated Wayland variables were inherited.

Each ordinary MCP desktop request rechecks the selected server through the
bounded helper; a cached Python X11 proxy does not cache the backend decision.
The metadata helper also enforces the boundary for direct library operations
that use it. This is not an implementation of Wayland portals or partial native
Wayland control. Xwayland versions predating the identification extension have
not been qualified; absence of the extension alone is not a universal proof
about an arbitrary legacy or custom server.

Six focused regression tests cover missing-display behavior, authoritative
protocol detection with no environment hints, unrelated hints on an explicit
X11 target, no-dispatch preflight, and diagnostic availability. Existing
cancellation/privacy test doubles explicitly supply the new backend preflight
contract; their original assertions remain unchanged.

[The real Weston/Xwayland qualification](WAYLAND-BASELINE.md#rejection-fix-qualification) covers three unsupported scenes and 12 actual MCP refusals, with an unchanged independent GTK oracle. A separate native Xvfb session remains ready despite stale Wayland environment hints.
