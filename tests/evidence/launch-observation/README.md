# Launch observation evidence

2026-09-20: ordinary UID 1001, private Xvfb/XFWM4/session D-Bus, actual stdio MCP. The retained immutable-source run passed in 2.702 seconds; see results.json for source/environment. No shared application or registry was modified. The initial implementation also passed; a second run strengthened the independent counter to append PID records rather than trusting a fixture-local constant.

From a checkout with its own locked venv and a writable artifacts directory, run as an ordinary user:

```sh
LUDA_ISOLATED_TEST_DISPLAY=1 xvfb-run -a -s '-screen 0 1440x900x24 -nolisten tcp' dbus-run-session -- .venv/bin/python scripts/headless_tests.py --suite launch-observation
```

The suite creates only temporary desktop entries and owned GTK applications. It confirms captured PID/start generations, two actual same-process windows including an early decoy, pending and dispatch-only outcomes, no repeated launch, raw-schema refusal, and owned application reaping. This is not a document-readiness or singleton-routing claim. Unit tests independently check incomplete/truncated enumeration, PID reuse, cancellation and the overall deadline.
