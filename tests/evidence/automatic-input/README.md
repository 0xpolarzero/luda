# Automatic input and visible cursor integration

The agent keeps using the existing MCP tools. Runtime routing and feedback are
generic X11 features, with no Silo dependency or separate agent mode.

`summary.json` records the tested revision, hashes of the changed runtime files,
and counts. All tests used private desktops and synthetic fixture data. The
integrated MCP and guard runs used the explicitly selected root test account;
native toolkit and browser comparisons separately used Ubuntu UID 1000. Neither
account is a product default.

- **Unit suite:** 921 run, 920 passed, one optional actual-wheel-build regression
  skipped because this venv does not install `build-requirements.lock`.
- **Real MCP routing:** 12 checks in `mcp-routing.json`, with independent GTK
  event/text files, X11 focus/pointer observations and captured cursor pixels.
  This includes automatic click/scroll/drag/hover activation, consecutive clicks
  through the cursor, background text/invoke, moved-element feedback, and
  disabled/stale/covered refusal without unnecessary activation.
- **Regression suites:** MCP, cancellation, menus, input guard and keyboard guard
  passed. `headless.json.gz` preserves the complete source/environment receipt.
- **Pointer lifecycle:** five checks passed for exact click/wheel counts,
  generation-bound motion, held-input refusal, controller death and cancellation.
- **Cursor lifecycle:** real desktop pixels, preserved focus/pointer, click-through,
  acknowledged hide, stale timeout, EOF cleanup and restart passed.

See the separate [native](../automatic-input-native/README.md) and
[browser](../automatic-browser/README.md) evidence for broader application checks
and baseline comparisons. Unavailable Qt accessibility and existing GTK4 semantic
provider errors remain limitations; no production catalog qualification is inferred.

Reproduce from a development checkout with its own venv:

```sh
.venv/bin/python -m unittest discover -s tests -p 'test_*.py'
.venv/bin/python tests/live_automatic_pointer.py
.venv/bin/python tests/live_cursor.py
.venv/bin/python tests/live_pointer_guard.py
env LUDA_ISOLATED_TEST_DISPLAY=1 xvfb-run -a \
  -s '-screen 0 1440x900x24 -nolisten tcp' dbus-run-session -- \
  .venv/bin/python scripts/headless_tests.py --suite mcp --suite cancellation \
  --suite menus --suite input-guard --suite keyboard-guard
```

Foreground fallback deliberately shares the physical pointer and keyboard. These
tests do not promise uninterrupted human use, arbitrary remote-viewer rendering,
or background support for all application actions. Pixels for covered windows
still require revealing and observing the window; screenshot safety checks remain.
