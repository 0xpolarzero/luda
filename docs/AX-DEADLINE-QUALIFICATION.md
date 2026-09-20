# Stopped accessibility provider: entire public call bound

AX-07 requires a hung accessibility provider to remain bounded by the subprocess deadline. Existing [client cancellation](../tests/live_cancellation.py) stops an owned provider but sends cancellation after 150 ms; lifecycle probes replace or kill providers/buses. Neither is evidence for a stopped-provider call allowed to complete without cancellation.

`tests/live_ax_deadline.py` adds that missing real-call observation. As ordinary UID 1001, it creates a private Xvfb, D-Bus, XFWM and GTK fixture, establishes healthy accessibility and independent text/click state, then sends SIGSTOP **only to the owned GTK provider**. `/proc` confirms the provider is stopped before public `desktop_inspect` starts and remains stopped when the result arrives. One actual persistent stdio MCP connection is used throughout.

The harness sends no cancellation notification, does not cancel the request future and does not stop the AX worker. It times the entire call from request dispatch through received result. Its external failure watchdog is seven seconds: the existing five-second AX subprocess bound, up to one second for cleanup/reap, and one second for target/transport overhead. Production deadlines are not enlarged. If the watchdog expires, the case fails; harness cleanup is not counted as deadline success.

## Recorded result

All seven assertions passed on the first run:

- Healthy accessibility exposed ten nodes and an editable field; independent app state held the synthetic sentinel with zero button actions.
- The entire stopped-provider `desktop_inspect` call returned **`ACCESSIBILITY_UNAVAILABLE`, effect `none`, in 1.067 seconds**, without client cancellation.
- The actual AX worker's PID/start-time identity was observed while pending. It exited before recovery; no worker or other server descendant remained.
- `desktop_status` remained usable after the provider failure, taking under 1 ms in this run, with no recovery quarantine pending.
- After SIGCONT, a fresh inspection on the **same MCP connection** recovered all ten nodes. The independent fixture text and click count remained unchanged after a further 300 ms observation.
- Outer cleanup found zero surviving tagged processes. No runtime change was necessary.

**This result did not exercise the five-second subprocess kill path.** libatspi's earlier timeout allowed the worker to return a typed failure first. It establishes observed bounded entire-call completion against a stopped real provider, not causal proof that the outer five-second deadline killed a GTK accessibility request.

Separate existing tests establish generic subprocess mechanisms: [`test_overall_deadline_bounds_multiple_commands`](../tests/test_operation_runtime.py) runs two real subprocess commands inside a shorter shared operation deadline and asserts `TIMEOUT`; [`test_timeout_kills_descendant_before_delayed_effect`](../tests/test_process_cleanup.py) times out a real parent/child process group and independently verifies the delayed file write never occurs. Both focused tests passed on this snapshot. They remain separate generic deadline/cleanup evidence, not substituted real-provider five-second-kill evidence.

Evidence is retained in `artifacts/ax-deadline/attempt-1/`, including individual cases, worker identity, source fingerprints and cleanup. Before/after source fingerprints matched `c0a50876fb397f0f8726c7a9241fc43e5bd0ca15d9d18a421d6c486095e1308d`; this report was added afterward.

## Reproduce and scope

From a writable checkout as the ordinary desktop account:

```sh
.venv/bin/python tests/live_ax_deadline.py
```

The script creates the isolated desktop itself. A root-owned checkout needs an ordinary-user-writable `artifacts/ax-deadline` parent. Each default run uses a separate artifact directory; the outer setup/cleanup watchdog is 35 seconds. It requires the normal GTK3/AT-SPI/Xvfb/XFWM live-test dependencies and downloads nothing.

Scope is one stopped GTK application, not a dead accessibility bus, a stopped display server, a whole-OS freeze, every provider failure mode or a universal latency guarantee. The resumed process and its application state are preserved through the test; no user desktop or unrelated process receives input or signals. AX-07 catalog-level qualification is not automatically upgraded by this bounded observation.
