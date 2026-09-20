# Native paste: bounded independent observations

Hosted desktop run [35506268196](https://github.com/0xpolarzero/luda/actions/runs/35506268196), source `e08bc91`, failed native `literal-paste-2` after a fixed 120 ms observation delay. MCP's delayed-paste regression and the other 16 suites passed. Original native log, assertion receipts and independent final state are retained unedited. That final state is exactly the expected `tabs\there\n`, although the actual value sampled at the failure and paste response were not retained. This establishes eventual expected text, not the precise timing or cause of the failed sample.

The old loop also cleared the editor without independently observing the empty state. The revised loop uses the same bounded read-only `fixture_oracle.wait_text` as the MCP regression: prove empty baseline, dispatch one paste, retain its full return or typed error, then observe independent state for at most two seconds. Every iteration records response, last state, samples and timings before asserting. Input is never retried. Semantic replacement readback also uses the bounded oracle. Other native checks are unchanged.

The existing CI native row now enables the fixture's 450 ms delay before its real GTK default paste handler. No application setter substitutes for paste. An assertion checks the cumulative request count is exactly one per iteration and the configured delay occurred. The default standalone fixture remains undelayed unless explicitly selected.

Actual ordinary UID 1001 private Xvfb/XFWM/D-Bus run `1789901986655146081` passed in 9.115 seconds with unchanged source inventory, based on `1e39272` plus this fixture correction. All five post-dispatch waits exceeded the former 120 ms observation interval: 456, 463, 452, 804 and 481 ms. Request counts were respectively 1 through 5. The complete native suite, including literal Unicode, empty/long replacement, refusal checks, pointer checks and stopped-provider recovery, passed. This qualifies the observation mechanism under deliberate delayed GTK delivery, not a retrospective diagnosis of the hosted failure.

Reproduce on a fresh private desktop:

```sh
runuser -u silo-desktop -- env LUDA_ISOLATED_TEST_DISPLAY=1 \
  xvfb-run -a -s '-screen 0 1440x900x24 -nolisten tcp' \
  dbus-run-session -- .venv/bin/python scripts/headless_tests.py --suite native
```

Ensure the worktree's `artifacts` directory is writable by the desktop account. Three shared oracle units also pass: `PYTHONPATH=tests .venv/bin/python -m unittest test_fixture_oracle`. No production source changes, mutation retries or user-desktop input are involved. The overall suite deadline is unchanged; the fixed sample delay becomes an explicit two-second observation bound. Gzip evidence uses zero mtime and contains synthetic fixture text only.
