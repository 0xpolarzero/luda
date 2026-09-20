# Chromium native keyboard compatibility probe

Date: 2026-09-20. Bounded investigation, not a supported input route.

Environment: ordinary `ubuntu` test account, private Xvfb, XFWM without compositor,
Google Chrome for Testing 153.0.8010.12, Playwright 1.63.0. Each browser run used
`tests/live_owned_browser.py` at integration `c5d259b`, which checks independent
HTTP/DOM text, key, and composition events. The existing first 27 browser cases
passed before the native IME precondition failed. No shared desktop was used.

The native precondition focuses the owned field, sends `ctrl+shift+u`, then
`3`, `0`, `6`, `b`, and requires an actual trusted composition event plus active
composition state. Dispatch success alone is insufficient.

| Temporary probe | Result |
| --- | --- |
| Private XI2 pair, `send_core=True`, usual connection-bound XTest keys | No new DOM key events; no composition |
| `xdotool key --window <browser-top-level> ctrl+shift+u 3 0 6 b` (direct core XSendEvent) | No new DOM key events; no composition |
| Private core-enabled pair plus scoped `XISetClientPointer(browser-top-level, private-pointer)` before native keys, restoring original application ClientPointer afterward | No new DOM key events; no composition |

These changes were reverted; a second private device pair was **not** implemented
because it did not resolve the observed failure. Application ClientPointer changes
are also client-wide and would require separate same-client human concurrency
qualification even if they helped.

A separate private Chromium launch checked the focus-proxy hypothesis:
`xdotool windowactivate --sync <browser-top-level>` followed by `getwindowfocus -f`
returned the same window ID as `wmctrl`. `xwininfo -id <browser-top-level> -tree`
reported zero children. Thus the tested Chromium window had no hidden input child
to target instead.

As a control, a GTK3 fixture with a preselected entry received all 20 private
core-enabled keyboard events while a separately focused human fixture received
all 161 concurrent `b` keystrokes. Sampled human focus remained unchanged after
every action. The agent pointer was never moved during that control. This proves
neither continuous focus safety nor Chromium compatibility.

## Source explanation and its limits

Chromium tag `153.0.8010.12` resolves to
`971a7443b0c9b0a9b2860529b33331b76077ec62`.

- [TouchFactory device-list update](https://github.com/chromium/chromium/blob/971a7443b0c9b0a9b2860529b33331b76077ec62/ui/events/devices/x11/touch_factory_x11.cc#L108)
  assigns `virtual_core_keyboard_device_` for each master keyboard encountered.
  The final encountered master is the one retained.
- [TouchFactory key filtering](https://github.com/chromium/chromium/blob/971a7443b0c9b0a9b2860529b33331b76077ec62/ui/events/devices/x11/touch_factory_x11.cc#L174)
  rejects XI2 key events from any other master keyboard. The cached selection does
  not consult the target application's ClientPointer.
- [Event translation](https://github.com/chromium/chromium/blob/971a7443b0c9b0a9b2860529b33331b76077ec62/ui/events/x/events_x_utils.cc#L417)
  maps rejected XI2 device events to an unknown event type. Core key events have
  a separate translation branch, but that fact did not make targeted XSendEvent
  work in the observed application state.

This is a concrete source-level obstacle to generic private XI2 keyboard support.
It does not, on its own, explain every failed synthetic-core-event route or prove
that no other Chromium-compatible implementation exists. Owned-browser CDP input
and native OS IME input must remain distinct claims.
