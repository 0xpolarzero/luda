# Automatic input compatibility validation

2026-09-20, integrated runtime through `e56346a` and `2aeac4b`.
The full unit suite on `2aeac4b` ran 983 tests successfully (one optional test
skipped). After integrating these evidence and documentation changes, all 16
contract and live-inventory checks passed on `e05bf60`.

All live runs used isolated Xvfb/XFWM sessions and an independent worktree venv.
Browser tests ran as the explicitly selected ordinary test account, with
Chromium 153.0.8010.12 and disk-backed temporary profiles.

- `owned-browser.json`: 45/45 real MCP cases. Background addressed typing and
  selection retain human keyboard focus. Native keys automatically foreground
  the owned browser and produce trusted DOM events and exact text. Real native
  IME preedit exercises the conservative composition refusal boundary.
- `owned-secret.json`: 19/19 cases, including native clipboard paste and
  secret redaction with independent application effects.
- `private-input.json`: 9/9 GTK3 cases with concurrent human device input,
  independent application file oracles, sampled human focus, and cursor pixels.
- `shared-fallback.json`: 5 checks of a plain core-only Xlib app with no
  AT-SPI toolkit: click counter, exact typed text, actual core keyboard focus,
  and no text in the separate human app.

Commands: `.venv/bin/python tests/live_private_input.py` and
`.venv/bin/python tests/live_shared_fallback.py` create their own displays.
Run `tests/live_owned_browser.py --executable <chromium>` and
`tests/live_owned_secret.py --executable <chromium>` under an ordinary account
in separate Xvfb, D-Bus and XFWM sessions with `LUDA_ISOLATED_TEST_DISPLAY=1`,
private XDG directories, and disk-backed TMPDIR.

A native-browser regression was caught by the independent DOM oracle: both
Luda and xdotool dispatched keys with correct X11 focus but no DOM effect while
CDP focus emulation remained enabled. The native handoff now disables emulation
and activates the page before injection; the same oracle passes. X11 focus
checks use actual keyboard focus, not potentially stale WM active-window
bookkeeping.

These are bounded fixtures, not universal toolkit, window-manager, viewer or
application qualification. Shared fallback intentionally uses the ordinary
mouse/keyboard and may interrupt user input. Independent GTK input does not
remove application-level focus side effects or shared document state.
