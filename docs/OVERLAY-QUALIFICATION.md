# Overlays, attention and dialog defaults

`tests/live_overlays.py` exercises three workflows against an owned GTK3 fixture through the public Desktop API, using independent application counters. The opt-in matrix suite `overlays` runs it with private Xvfb/XFWM/D-Bus/XDG state as the ordinary desktop account.

- A GTK override-redirect help popup with the tooltip window-type hint appears over a previously observed button. Attempting the old point returns `OCCLUDED_TARGET`; neither the underlying button nor popup receives a click. A fresh observation identifies its owner. Explicit Escape dismisses the help; a newly observed click then increments the intended button exactly once.
- A fixture notification window deliberately takes focus. An action using the old owner and snapshot is refused, preserving the original counter. The test explicitly dismisses the notification and observes the intended owner regain focus.
- A modal dialog changes its default from Save to Cancel. Explicit invocation of the observed Save button still saves exactly once, without invoking Cancel. Deliberate Return would follow the application's current default; Luda does not reinterpret it as a previously seen button.

The ordinary-UID local matrix passed all three workflows in 4.036 seconds, with unchanged source fingerprint and no surviving tagged processes. Initial harness attempts failed because the default screenshot was resized and because the low-level invoke helper omitted the required action name; their logs remain under the local matrix artifacts. Corrected tests request a native-sized screenshot and explicitly invoke `click`.

This fixture establishes the listed target checks, not every notification daemon, real automatic GTK tooltip, tray implementation or theme. It uses a constructed tooltip-type popup and attention window. Screenshot layout checks cannot detect every same-window content change. No runtime change was needed for these cases.
