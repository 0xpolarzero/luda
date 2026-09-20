# Geometry qualification

`tests/live_geometry.py` runs only in an explicitly isolated Xvfb/XFWM session. Both decorated and borderless GTK3 windows passed ten grouped cases on ARM64 Ubuntu 24.04 at native 1440×900:

- Screenshot widths 1280, 777 and 321: PNG dimensions match metadata; a known solid application color is preserved at the target; independently queried X pointer positions match the screenshot-to-root coordinate mapping.
- Every client rectangle matches independently parsed `xwininfo`; the borderless client and frame rectangles coincide.
- Exact image width/height and negative coordinates are rejected. The last native pixel of a fullscreen window remains reachable.
- Moving partially offscreen invalidates the old snapshot. The visible client region remains reachable after observing again; negative image coordinates remain invalid.

These checks are now part of the isolated headless runner and hosted desktop workflow. They establish fractional **screenshot resizing**, not compositor fractional scaling. Root image pixels are the current coordinate contract; physical monitor pixels or host viewer points must not be substituted.

Multi-monitor arrangements, mixed monitor scaling, rotation and physical hotplug remain unqualified. Xvfb's fixed single output does not reproduce those cases. In particular, same-root-size monitor topology changes are not currently represented in snapshot signatures. A changed root size is rejected, but that does not prove detection of every topology change.
