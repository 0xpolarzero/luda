# Native application CI

`.github/workflows/native-apps.yml` runs four required suites on an ordinary
Ubuntu 24.04 GitHub-hosted runner account:

| Suite | Independent evidence |
| --- | --- |
| Mousepad file workflows | 10 assertions: overwrite, unsaved-close decisions, read-only refusal and exact file bytes |
| Thunar file workflows | 9 assertions: folder creation/rename, binary copy, duplicate conflict and permanent deletion, including cancellation |
| Native window states | Real GTK windows, X properties and pointer position for move/resize/maximize/fullscreen/minimize/restore/workspaces/raise/hover |
| MCP applications | Actual MCP discovery and launch, pause enforcement, independent process argv and visible window, operation history |

Applications and system dependencies are installed only in the CI setup
step. Python runtime dependencies use `requirements.lock` with hash checking;
the project is then installed with `--no-deps`. Browser qualification is a
separate concern and no browser cases are skipped or reclassified by this job.

Run locally after installing the same dependencies:

```sh
.venv/bin/python scripts/native_app_tests.py
```

Root is rejected because it bypasses the read-only file fixture. The script
creates one private Xvfb, session bus and Xfwm4 session per suite. Private
XDG config/data/cache/runtime paths are established before the bus starts;
inherited desktop/session addresses are removed. Each suite has a 120-second
limit and its whole owned process group is terminated even if its launcher
already exited. Fixtures operate only on owned apps and temporary files.
Unit tests verify failure propagation and that both a timed-out launcher
and an already-exited launcher cannot leave a descendant to perform a late
filesystem write.

Every suite failure or timeout makes the job fail. `artifacts/native-apps`
contains per-suite logs and a JSON report with results, elapsed times, source
file hashes, OS, architecture, Python, account and installed application
versions. The workflow uploads all fixture evidence even on failure.

The initial local run on Ubuntu 24.04 ARM64 passed all four suites (about
26 seconds total), and all three runner cleanup/error tests passed. Hosted Ubuntu x86-64 execution also passed all four suites in [run 35479304982](https://github.com/0xpolarzero/luda/actions/runs/35479304982), on Ubuntu 24.04.5, Python 3.12.14, UID 1001. Hosted Xvfb remains distinct from a fresh Linux environment guest.
