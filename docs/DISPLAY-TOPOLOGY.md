# Display topology and screenshot validity

An unchanged root size does not establish an unchanged display layout. Each
observation now captures the X-server generation, root geometry and bounded
RandR metadata and logical active-workspace context before and after screenshot capture. Client and popup pointer
validation compare the same metadata before using a snapshot. A changed layout
returns `DESKTOP_CHANGED` during capture or `STALE_OBSERVATION` during targeting.
The agent should observe again; Luda does not change display configuration.

Metadata includes controller/output identities, configuration timestamps,
controller position/size/rotation, current fixed-point transforms, panning and
RandR 1.5 logical monitors where available. Arrays are capped at 64 entries;
native calls run in the existing bounded helper process. Output names, EDID and
connector properties are not collected. Missing RandR 1.3 or libxrandr2 is an
explicit diagnostic failure, not silent resolution-only validation.

Tool responses expose a compact layout ID and monitor rectangles, including
screenshot-space `image_bounds` on observations. Disabled controllers and raw
transform/panning arrays stay internal; the layout ID covers them too. Doctor
uses native monitor bounds. On RandR older than 1.5, active controller rectangles
are explicitly labeled as such and primary-monitor status is unknown.

The API follows the [RandR protocol](https://www.x.org/releases/current/doc/randrproto/randrproto.txt)
and libXrandr's public ABI. Screenshot and pointer coordinates still use X11 root
pixels; physical monitor millimeters do not define their scale. This change
detects sampled layout differences. It does not make input atomic with hardware
hotplug or qualify mixed-DPI, rotation, panning or every multi-monitor workflow.
Changes that occur and revert between reads can remain undetected.

`live_geometry.py` adds and removes a real logical monitor on a private Xvfb
without changing root size. It checks independent `xrandr` output, rejection of
the old snapshot and acceptance after observing again. Unit tests also cover
popup targeting, layout changes during capture and bounded native arrays. Actual
Linux/KasmVNC 1.5.0 and Xvfb both expose the required metadata in this ARM64 guest.

## Logical workspace context

The topology fingerprint also includes bounded `_NET_CURRENT_DESKTOP` and, when
present, `_NET_NUMBER_OF_DESKTOPS` root properties. This is logical desktop
context, not a physical monitor transform. Public `workspace` metadata reports
`status="available"`, its zero-based `index` and optional `count`. Workspace zero
is distinct from `status="unsupported"` on a WM that does not expose or advertise
this EWMH feature. A malformed property, out-of-range index, incoherent count,
or advertised-but-missing current workspace fails closed; no workspace is guessed.
Reads share the existing bounded native helper and introduce no polling service.

An external or second-client switch now invalidates current-layout snapshot use
when its different workspace is sampled, even if a sticky window retains the
same geometry, identity and focus. Client/popup targeting, OCR and image-match
targets reuse the existing topology comparison. A historical image-match source
still needs the same X server and an unexpired retained image, but intentionally
does not need the original active workspace. Changes that revert entirely
between checks remain undetectable; no cross-client continuous history is claimed.
Explicit switches issued by this backend already expire its own screenshots
before dispatch, including switch-and-return.

`live_workspace_snapshots.py` additionally uses two actual Desktop instances and
an independent `wmctrl` switch against an owned sticky GTK window. After explicitly
reacquiring that same target, its complete window signature matches, yet the old
screenshot is refused before pointer input. Independent app clicks remain zero,
current workspace is read via `xprop`, and historical image access remains allowed.
See [retained evidence](../tests/evidence/workspace-context/README.md).
