# Display topology and screenshot validity

An unchanged root size does not establish an unchanged display layout. Each
observation now captures the X-server generation, root geometry and bounded
RandR metadata before and after screenshot capture. Client and popup pointer
validation compare the same metadata before using a snapshot. A changed layout
returns `DESKTOP_CHANGED` during capture or `STALE_OBSERVATION` during targeting.
The agent should observe again; Luda does not change display configuration.

Metadata includes controller/output identities, configuration timestamps,
controller position/size/rotation, current fixed-point transforms, panning and
RandR 1.5 logical monitors where available. Arrays are capped at 64 entries;
native calls run in the existing bounded helper process. Output names, EDID and
connector properties are not collected. Missing RandR 1.3 or libxrandr2 is an
explicit diagnostic failure, not silent resolution-only validation.

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
Silo/KasmVNC 1.5.0 and Xvfb both expose the required metadata in this ARM64 guest.
