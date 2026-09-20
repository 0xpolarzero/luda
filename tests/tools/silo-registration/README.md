# Patched Silo registration CI

The `Silo native registration` workflow checks out the exact upstream Silo commit
required by `integrations/silo/apply.py`, applies every ordered patch and executes
the actual resulting sources. It runs the three frontend test files, full
TypeScript checking and `codex_desktop::tests` including the five normally ignored
real Codex CLI cases. Missing CLI, version mismatch, native skipped cases or a
missing expected real-CLI test fail the job. The pinned CLI comes from the existing
`tests/tools/codex-cli/package-lock.json`; it uses temporary profiles without model
calls or sign-in. There are no copied native module stubs.

Ubuntu 24.04 uses the upstream Linux build dependencies, Node24 and Rust1.94.0.
The test-only `TAURI_CONFIG` override empties bundle resources/external binaries,
so no microsandbox runtime is downloaded or launched. Synthetic GitHub build
values are public placeholders. Frontend tests mock Tauri; native tests execute
real Rust and real CLI cache/config operations. Passing does not establish packaged
application, macOS dialog, SSH connectivity or VM operation readiness. The optional
Chromium layout harness from patch0015 is separate and is not run by this job.

Reproduce after installing the workflow dependencies and the locked CLI:

```sh
python tests/tools/silo-registration/run.py /absolute/clean-pinned-silo \
  --codex /absolute/luda/tests/tools/codex-cli/node_modules/.bin/codex \
  --output /absolute/test-evidence
```

The checkout must be disposable: the runner applies patches and installs its locked
npm dependencies. Logs, exact argv, patch hashes and completion status are written
under the selected output directory, including on failure. Rust cache accelerates
later runs but sources and lockfile remain authoritative. Hosted execution is only
claimed once that workflow actually completes; adding the workflow itself is not
a hosted pass.
