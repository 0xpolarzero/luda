# Matrix Xvfb startup diagnostics

Hosted run [35499802558](https://github.com/0xpolarzero/luda/actions/runs/35499802558),
source `037c3cc`, failed the first browser suite before fixture input:
XFWM could not open `:99`. The exact failure log is retained here. Other suites
starting successfully does not repair or erase that failure. The prior
`xvfb-run` invocation discarded Xvfb/xauth stderr, so the artifact cannot
establish whether the cause was server startup/death, authorization or another
connection failure. No specific race is claimed as reproduced.

The matrix now retains each `xserver.log` using `xvfb-run -e`. Before starting
XFWM or a fixture it probes the inherited private display with read-only
`xdpyinfo`, bounded by five seconds with per-probe deadlines. A missing display
fails before any GUI workflow is started. `startup.json` and the matrix result
record the last startup stage (`display_connect`, `window_manager`, or
`fixture`), connection-attempt count and elapsed time. No Xauthority cookie is
read or reported. If the wrapper never returns a startup report, the result
explicitly says `launcher` / `reported: false`; that is absence of a report,
not proof that its command never started.

Only connection observation repeats. A dead WM is not restarted and fixture
input is never replayed. Existing overall deadlines and owned-process cleanup
remain in place. A successful probe proves connection at that instant, not
continued server availability or repaired hosted behavior.

Five added focused cases cover delayed read-only readiness, bounded probe
timeouts, absent-display refusal before launch, dead-WM no-retry, and actual
private Xvfb with valid versus a separately owned empty authority file. The
existing Firefox argv test was updated to mock this new read-only precondition;
its initial mock failure was a harness dependency mismatch, not GUI evidence.
The full focused module passes 15 tests as UID1001.

One local ordinary-account private `owned-browser` matrix run passed in 18.965s
with unchanged source and no owned survivors. Its actual X-server log was
retained and empty; `startup.json` shows one successful connection probe.
`result.json` records the exact source/environment. The only change after that
live run was the focused Firefox test's missing mock and these evidence files.
No new hosted pass or universal startup reliability is claimed.
