# Real XFCE tray menu qualification

MENU-07 requires identifying the actual application/menu instead of blind
panel-wide actions. A private **real xfce4-panel systray** embedding an owned
`Gtk.StatusIcon` supports a scoped screenshot route with current Luda. Semantic
tray identity is still unavailable: the panel tree exposes unnamed containers,
and the icon application has no managed top-level window.

`tests/tray_fixture.py` owns the icon, its unique tooltip, a one-item menu and a
counter written independently by the menu callback. `tests/live_tray.py` uses
public Desktop methods for every input. Run as the ordinary desktop account:

```bash
.venv/bin/python tests/live_tray.py
```

Requires `xfce4-panel` with its systray plugin, GTK3, Xvfb and Xfwm. The launcher
creates private XDG configuration before private D-Bus, writes a single-panel
configuration containing only systray, and launches its own X server/window
manager. It does not touch the user's panel or settings. A 45-second runner bound,
owned process cleanup and source fingerprints are recorded. Results and PNGs
are retained under a unique `artifacts/tray/<time_ns>/` directory.

## Observed workflow

1. The independent application state reports its icon actually embedded in the
   tray. Public window enumeration finds the owned panel PID. Its accessible tree
   contains an unnamed frame, two panels and a filler; no icon identity/action.
2. Hovering the inactive panel refuses `FOCUS_CHANGED`. Explicit panel activation
   succeeds on the tested Xfwm. A fresh screenshot and public hover over its
   observed icon reveal the unique tooltip **Luda owned tray**.
3. Public right-click at that same observed icon opens the screenshot-visible
   **Increment owned counter** menu. Public accessibility still exposes only
   unnamed panel containers, and observation's `popups` array is empty.
4. Deliberate Down/Return on that observed single-item menu increments the
   independent counter from zero to one. These calls report dispatched input;
   the application counter proves the effect.

The initial icon, tooltip and menu screenshots were visually inspected during
qualification. The reusable fixture uses that observed fixed English layout
(icon center 24,18 on its private 1280-wide display), saves fresh screenshots at
each stage, and checks the independent effect. It is **not** an OCR/icon-recognition
algorithm and does not autonomously read its saved screenshots. The screenshot
route is distinct from semantic discovery or an ordinary top-level window posed
as a tray. The final fixture selects only the panel process it launched.

## Source-bound result

Final run `1789874720505513619` on base `f2f7a84`, fingerprint
`02353b0e6358647bf6644d71f3826f5ae443d1936c46c57eda8c40f8cf391f20`, passed with
unchanged before/after source and no tagged survivors. Ordinary UID 1001,
Ubuntu 24.04 ARM64; `xfce4-panel 4.18.4-1ubuntu0.1`, GTK
`3.24.41-4ubuntu1.3`. The preceding complete fixture run
`1789874699111835025` also passed; the final change restricted window selection to
the owned panel PID.

Exploratory artifacts retain the initial unnamed tree, screenshot-visible
identity and menu, and exact focus/activation outcomes. An early harness call
incorrectly used `pointer(kind='hover')` and correctly received INVALID_ARGUMENT;
the actual public hover method worked after explicit activation. One exploratory
cleanup attempt found panel termination slow; the retained fixture escalates
only its owned process after a bounded wait and the outer runner audits survivors.
No runtime refusal was bypassed.

## Limits

The menu's owner is visually identified but has no Luda app-specific window or
popup handle. Keyboard dispatch remains bound to the panel's active-window
generation while the GTK menu grab routes events. This does not provide semantic
menu-owner generation validation, prevent a competing grab, or qualify other
panels' activation behavior. Direct menu pointer targeting outside the panel,
multiple similar icons, changing menu layouts, StatusNotifierItem/AppIndicator,
Wayland, global application menus and tray replacement races are unqualified.
Gtk.StatusIcon is deprecated but remains a real installed XEmbed tray path.

No runtime extension was needed for this bounded workflow. The catalog remains
release-unqualified; successful counter activation must not be presented as
complete semantic tray support. A future owner-aware tray API needs a separate
identity design and review rather than relaxing focus or popup ownership checks.

The optional `tray` qualification-matrix entry runs the same private-session
launcher and checks for `xfce4-panel` before launch. Registration does not
automatically qualify the requirement.
