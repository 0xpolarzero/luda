# Bounded CPU scheduling pressure

`tests/live_cpu_pressure.py` adds actual Linux CPU contention to the PERF-10 evidence. Existing resource-limit tests cover memory/file-descriptor limits; stopping a provider tests a different failure mode. This fixture keeps the provider runnable and measures competing CPU execution and run-queue delay. It does not qualify PERF-10 generally.

Run as the ordinary desktop account through the opt-in matrix:

```sh
.venv/bin/python scripts/qualification_matrix.py --suites cpu-pressure --timeout 90
```

The controller requires at least two allowed CPUs and normal priority. It remains unpinned, while a private Xvfb/D-Bus/XFWM/GTK desktop and actual stdio MCP service inherit one selected CPU and nice 15. Two owned nice-0 arithmetic workers run on that same CPU. No shared display, global scheduler/cgroup change, whole-machine load, or stopped provider is involved. Linux autogroup membership is recorded: nice 15 is a scheduling input, not a promised CPU quota.

The load phase has independent limits: each worker exits after 25 wall-clock seconds and has a 30-second CPU limit; the controller imposes a 23-second pressure-response deadline. Every MCP call has a 15-second client deadline. An outer matrix watchdog bounds the entire run and checks tagged-process cleanup. These are watchdog bounds, not real-time scheduling guarantees.

The fixture first establishes baseline text, then makes exactly one text-replacement request under load. It records the response and effect, queries status, ends load, checks independently persisted GTK widget text, checks a short interval of state stability, and makes a distinct explicit recovery request using a fresh inspection. It never retries the pressure mutation. Stable text cannot prove that an identical operation was never replayed; this experiment makes no such inference.

## Retained runs

Both runs were UID 1001, CPU 0, with the normal-priority watchdog allowed CPUs 0–7. Full results, public-tool traces, process/thread scheduling samples, and cleanup evidence are retained under the corresponding `artifacts/qualification-matrix/` run directory.

| Run | Outcome | Load CPU / wall seconds | Pressure mutation | Status | Recovery mutation |
| --- | --- | --- | --- | --- | --- |
| `run-1789879169871269615` | First attempt passed | 5.362 / 5.505 (97.4%) | 267 ms | 0.861 ms | 193 ms |
| `run-1789879278827068542` | Passed after adding per-thread/overlap evidence | 5.333 / 5.455 (97.8%) | 344 ms | 0.745 ms | 183 ms |

The second run passed eight grouped assertions in 10.722 seconds. Both load-worker lifetimes enclosed the entire pressure mutation/status interval. Xvfb, XFWM, the GTK application, controller actor, and Luda were independently observed at nice 15 on CPU 0. The text operation reported verified success and the independent widget oracle matched all 23 Unicode code points, including Japanese text and the trailing newline. Post-load state remained stable and the distinct recovery text, including an emoji sequence, matched exactly. No owned processes survived cleanup.

Across the measured load window, surviving GTK threads accumulated 18.586 ms CPU execution and 43.426 ms run-queue waiting; surviving Luda threads accumulated 2.528 ms CPU execution and 17.785 ms run-queue waiting. These are differences in Linux per-thread `schedstat`, summed over threads present at both samples. They exclude short-lived worker processes and vanished threads; they are not total request CPU usage or latency attribution. Raw samples retain process identities and autogroup information.

The second run's source fingerprint was `adeae959f7dde5f6f6cde64307388894699906b68dfcfa2c8a7a221f1973c1db`, unchanged during execution. This explanatory document was added afterward. Ten matrix contract tests and eight inventory tests also passed.

## Scope

This is successful operation under one measured scheduling-contention scenario. It did not force or exercise a timeout/resource-error response, sustained system-wide starvation, OOM, disk exhaustion, or arbitrary application behavior. The harness can record a typed bounded failure with an honest none/uncertain effect, but that branch is not claimed as live-qualified by these successful runs. No production runtime change was required and no catalog qualification status changed.

## Integrated matrix check

The `cpu-pressure` matrix entry passed again as UID 1001 on main `e75f154`
in 9.445 seconds, retained in `artifacts/qualification-matrix/run-1789879611309772534/`.
The full run fingerprint was `a112b270c38b3474e027234b4ed48dff2e2b786f8c98e99f16b4ab9e02404f7b`,
unchanged throughout both suites. Eighteen matrix/inventory contract tests passed.
This integration check preserves the scope and limitations above.
