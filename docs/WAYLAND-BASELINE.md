# Private Wayland rejection baseline

On runtime `22e10c0e60801c4a221365253a1a656fc97b8ef8`, a private ordinary-UID 1001 Weston 13.0.0 headless/Pixman session with Xwayland 23.2.6 demonstrated missing explicit Wayland rejection. These are test-only Ubuntu packages (`weston 13.0.0-4build3`, `xwayland 2:23.2.6-1ubuntu0.8`), not runtime installer dependencies. The shared display was never used.

The compositor owned private Wayland socket `luda-wayland`, private XDG runtime and D-Bus session, and its Xwayland display `:0`. `xdpyinfo -queryExtensions` reported `XWAYLAND (opcode: 150)`. The installed server version independently reported Xwayland 23.2.6.

| Scene | Actual baseline outcome |
|---|---|
| Pure Wayland; no DISPLAY | Doctor ready=false/display unavailable; observation `DISPLAY_UNAVAILABLE`, effect none. No explicit unsupported-session classification. |
| Xwayland; Wayland session hints present | Doctor ready=true; observation succeeds, despite support text saying Wayland unsupported. |
| Same Xwayland server; WAYLAND_DISPLAY and XDG_SESSION_TYPE removed | Doctor ready=true; observation still succeeds. Environment-only detection would miss this scene. |
| Owned GTK X11 input fixture under Weston | Public window enumeration returned no windows, so no mutation target could be selected. Independent widget text stayed empty and key-event list stayed empty. This does not prove mutation rejection at the backend boundary. |

Raw first doctor/extension probe: `/workspace/luda-wayland-run/`. The initial mutation experiment in `/workspace/luda-wayland-run-2/` failed with `StopIteration` because it assumed the fixture appeared in public enumeration. `/workspace/luda-wayland-run-3/` retains the corrected explicit empty-window diagnostic, GTK state oracle, extension listing and compositor log. No error was converted into a passing mutation assertion. All owned compositor and xterm processes were terminated; a subsequent PID inspection found none surviving.

`tests/live_wayland_probe.py` preserves the probe as an ordinary-UID private-session diagnostic. Provide an owned output directory, mode0700 XDG_RUNTIME_DIR beneath it, private `dbus-run-session`, and an interpreter with Luda dependencies. It owns and cleans up Weston, xterm and GTK processes. It returns nonzero while either Xwayland doctor scene incorrectly reports ready. The original experiments used the same probe with an explicit dependency-venv interpreter path; the committed version uses its caller's interpreter and repository-relative fixture path. This baseline does not qualify the fix or native Wayland controls.

A useful rejection contract must distinguish an explicitly unsupported Wayland/Xwayland session from generic missing display, expose a non-ready diagnostic and refuse input without effects. Detecting the authoritative XWAYLAND extension is necessary for this demonstrated hints-removed case; the absence of environment hints does not establish X11 support. Physical devices, native Wayland accessibility and non-Weston compositors were not tested here.

## Rejection fix qualification

The same private Weston/Xwayland setup was rerun with runtime fix `b580e37` on top of the baseline. Raw results are retained separately in `/workspace/luda-wayland-fixed-run/`; earlier baseline and failed-probe artifacts remain unchanged.

All three unsupported scenes—pure Wayland, Xwayland with session hints, and Xwayland with both hints removed—now report doctor `ready=false` and `display_error_code=UNSUPPORTED_BACKEND`. In each scene a real stdio MCP server rejected `desktop_observe`, `desktop_windows`, `desktop_press_keys` and `desktop_launch` with `UNSUPPORTED_BACKEND`, effect `none`: 12 negative calls total. Key/launch arguments deliberately used unknown probe identifiers. These assertions establish rejection before target handling, not authorization of a valid window or installed application. The owned GTK fixture remained empty with no key events, including a delayed check after all rejected requests.

A separate private native Xvfb server, still carrying deliberately stale `XDG_SESSION_TYPE=wayland` and `WAYLAND_DISPLAY` hints, exposed no XWAYLAND extension. Luda accepted that backend, doctor reported ready=true/display available, and `require_supported_backend()` succeeded. Detection therefore used the targeted X server rather than rejecting an unrelated native X11 server solely because of stale environment hints.

The revised fixture asserts these outcomes; the actual run passed. Post-run PID inspection found no owned Weston, Xwayland or Xvfb processes remaining. This is scoped evidence for WAY-01 rejection and WAY-05 avoiding an inference of native Wayland access from Xwayland. It does not implement native Wayland support, qualify every compositor, or prove capability detection on older Xwayland servers that do not advertise the extension.
