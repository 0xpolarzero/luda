# Independent paste oracle and retained hosted failure

Hosted desktop run [35505335068](https://github.com/0xpolarzero/luda/actions/runs/35505335068), source `aef930b`, failed `mcp-paste-independent-readback`; the other 16 native suites passed. The original log, independent final state and assertion results are retained unedited as `original-*.gz`. The final text was empty. The test did not retain the paste receipt and sampled after a fixed 150 ms, so neither delayed delivery nor a runtime input failure can be established from this evidence. A later local pass does not resolve that historical cause.

The old test also never independently established empty text after clearing. A stale state file containing the identical earlier payload could therefore falsely satisfy its final check. The revised test first observes the empty baseline, dispatches exactly one public MCP paste, saves the entire response before assertions, and polls only the independent atomic state file for at most two seconds. It saves the last state, sample count and timings on success or timeout. No mutation is retried. The same bounded oracle replaces the earlier fixed-delay semantic set-text assertion.

The CI MCP row now enables a 450 ms fixture delay. An opt-in `paste-clipboard` signal handler defers and then invokes the real GTK default clipboard paste handler once; it never supplies text through an application setter. The fixture records request count and dispatch times. Its normal path remains unchanged when the option is absent, including the native baseline suite.

Actual private ordinary UID 1001 Xvfb/XFWM4/D-Bus run `1789901017778853202`, based on `61b8c0a` plus these fixture changes, passed native (7.806 s) and MCP (3.781 s), with unchanged source inventory retained in `private-results.json.gz`. The empty baseline required two samples/21.6 ms. The public paste reply was `dispatched` after 227.7 ms. The independent post-reply wait required 476.6 ms/22 samples; the fixture recorded exactly one request and 451.0 ms before delivery. This actual path exceeds the old 150 ms post-reply observation interval. It demonstrates the improved oracle, not the cause of the historical hosted failure. No runtime source or user clipboard was changed by the test implementation.

Reproduce in an isolated desktop only:

```sh
runuser -u silo-desktop -- env LUDA_ISOLATED_TEST_DISPLAY=1 \
  xvfb-run -a -s '-screen 0 1440x900x24 -nolisten tcp' \
  dbus-run-session -- .venv/bin/python scripts/headless_tests.py --suite mcp --suite native
```

The worktree's `artifacts` directory must be writable by that account. Three focused unit tests cover delivery after 150 ms, stale prior payload refusal as an empty baseline, and missing/malformed state refusal: `PYTHONPATH=tests .venv/bin/python -m unittest test_fixture_oracle`. Evidence includes authored synthetic text only; gzip files use zero mtime.

Hosted source `d193031` subsequently passed [desktop workflow 35506123995](https://github.com/0xpolarzero/luda/actions/runs/35506123995), including all 17 private native suites. The retained `hosted-d193031-paste-evidence.json.gz` records the actual 450 ms delayed-paste regression: one request, independent empty baseline, 702.7 ms tool reply, then 444.7 ms/23 read-only samples until exact application text. This verifies the new observation contract on hosted AMD64 as well as local ARM64; it still does not identify the earlier failure's cause.
