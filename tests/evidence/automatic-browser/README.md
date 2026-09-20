# Automatic owned-browser routing validation

September 20, 2026; runtime revision `0bca5e0` plus the two test cases retained
in this commit. Explicit test account **ubuntu (UID 1000)** on new private
Xvfb/XFWM/D-Bus sessions, GTK simple IME, Chromium 153.0.8010.12 (Playwright
chromium v1243), Playwright 1.63.0. No shared `:1` interaction.

- `live_owned_browser.py`: **44/44 cases passed**. The added background type and
  select cases put a separately owned GTK window in front, then use ordinary
  MCP `desktop_type` / `desktop_select` calls without explicit browser activation.
  A page-origin HTTP oracle independently verifies exact text and selection;
  desktop window state verifies automatic foreground fallback. Core pointer
  location also remains unchanged during the typing case.
- Existing checks passed for native trusted input, Unicode/grapheme boundaries,
  protected-response redaction, download ownership, replaced-node/document and
  frame-scope refusal, active native IME preedit preservation, ordinary browser
  disconnect, and guardian/server/worker failure cleanup.
- `live_owned_pages_probe.py`: **8 recorded scope checks passed**. Multi-page
  owned-field refusal preserves native inspection, popup native completion works,
  and the original page's owned fields return after leaving multiple-page scope.
- `python -m unittest discover -s tests -p 'test_owned_browser*.py'`: **16 passed**.

`routing.json` contains only the two new cases. Compressed JSON files retain
all cases from both live suites. Fixtures and their payloads are synthetic;
the HTTP oracles listen only on loopback.

Reproduce with an explicit non-root test account, private Xvfb/D-Bus and XFWM,
an isolated XDG directory set, and a checkout-local venv:

```sh
.venv/bin/python tests/live_owned_browser.py --executable /absolute/path/to/chrome
.venv/bin/python tests/live_owned_pages_probe.py --executable /absolute/path/to/chrome
```

Both commands require `LUDA_ISOLATED_TEST_DISPLAY=1`. Browser installation for
this run used workspace storage because `/tmp` is a 512 MiB tmpfs; this changes
neither product installation nor browser selection defaults.

These results cover temporary Luda-owned Chromium HTML fields and the scoped
fixtures. They do not establish background DOM typing, existing signed-in browser
attachment, arbitrary rich editors, all browsers, or simultaneous human input.
No production catalog qualification is inferred from this run.
