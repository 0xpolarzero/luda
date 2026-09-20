# Independent X11 input experiment

Research only; no production device support added. Reproduce using the command
in `tests/prototypes/independent_input.py`. The probe compiles a tiny XI2/XTEST
helper into a temporary directory and creates a second master pointer/keyboard
on a **new private Xvfb**. Two separately launched GTK3 applications write their
own counters, entry contents, and popup visibility; XFWM manages their windows.
No shared desktop or Silo-specific integration is used.

The four asserted cases passed:

| Interaction | Independent application result | Desktop result |
| --- | --- | --- |
| Click visible background button | Intended counter increments | Core pointer unchanged; core keyboard focus and stacking change |
| Type with independently assigned keyboard focus, after entry selection | Intended entry receives `a` | Sampled pointer, core focus, active window and stacking unchanged |
| Click coordinates of a covered background button | **Covering human app's counter increments**; intended counter unchanged | Core pointer unchanged |
| Open background GTK menu | Intended popup becomes visible | Core pointer unchanged; core keyboard focus and stacking change |

Recommendation: do not introduce MPX to production in this implementation.
A second pointer can preserve human pointer position, but does not deliver the
requested background-window behavior under the tested window manager and does
not address covered windows. Semantic actions plus automatic foreground fallback
are the smaller initial design. Independent keyboard injection is potentially
useful later, but one preselected GTK entry is insufficient qualification of
widget focus, grabs, modifier state, multiple toolkits, or concurrent typing.

`results.json` records the actual experiment. Before/after sampling cannot rule
out transient interference. This is mechanism research, not a catalog support
claim or full concurrent-input acceptance test. UID 0 identifies the explicit
local test environment only; no product account selection is introduced.
