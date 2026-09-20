# Hosted input-generation fixture teardown failure

[Desktop contracts run 35486315531](https://github.com/0xpolarzero/luda/actions/runs/35486315531)
on `696e9d4` passed 15 of 16 headless suites, including `keyboard-guard`.
`input-generation` printed all its successful input assertions, then failed in
its final `Xvfb.terminate(); wait(timeout=3)` with `subprocess.TimeoutExpired`.
The failing process was the test's replacement private X server. This is distinct
from the keyboard cancellation baseline race fixed in `1adc376`.

The [successful earlier run 35486210870](https://github.com/0xpolarzero/luda/actions/runs/35486210870)
on `e987d22` used identical `live_input_generation.py`, headless runner, and guardian
source. Its input-generation log contains the same successful assertions without
a cleanup exception. Original hosted artifacts were downloaded, without alteration,
to `/workspace/luda-ci-evidence/run35486315531` and
`/workspace/luda-ci-evidence/run35486210870`.

The unchanged test passed locally as ordinary UID 1001 on ARM64. The exact reason
that the hosted Xvfb did not terminate in time remains unknown; the artifacts do
not establish a product input-cleanup failure or a regression between those commits.

## Narrow correction and verification

Only final teardown of this owned Xvfb now sends TERM, waits up to three seconds,
then sends KILL and waits up to three seconds when necessary. It records escalation
and the reaped return code. Failure to reap still raises and fails the test. It does
not retry any assertion, touch another PID, or modify production cleanup. Initial
X-server replacement still requires its original strict graceful termination.
Environment restoration runs even when final owned-server cleanup raises.

Five focused tests cover already-exited, graceful, timeout/escalation, unreaped,
and signal-error outcomes. A real fault mode,
`--exercise-stalled-xvfb-cleanup`, stops only the owned replacement Xvfb after all
input assertions and after closing the oracle's Xlib connection. It requires a
recorded escalation and a SIGKILL return code. A normal live run exercises graceful
cleanup. These logs are in `/workspace/luda-ci-contracts/artifacts/ci-contracts`.

An initial fault-injection probe stopped Xvfb before closing that Xlib connection,
which blocked the oracle's close operation. It was manually resumed and its log
retained as `initial-fault-oracle-close-blocked.log`; it is not passing evidence for
the stalled-cleanup fault. Moving the injected stop after the connection close
isolates the intended teardown condition. It does not explain the hosted stall.
