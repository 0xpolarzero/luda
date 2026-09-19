# Requirement-linked evidence

Run `.venv/bin/python scripts/qualify.py`. This executes the actual unit suite and writes `artifacts/qualification/unit.json`, including the source-file hashes, Git revision, environment, individual test outcomes and every requirement's evidence status. `docs/test-map.json` links stable requirement IDs to exact unittest IDs and records the limits of each mapping.

Three independent facts are retained:

- **Implementation:** not assessed, missing, partial or implemented. This is a reviewed claim in the map, not inferred from a test passing.
- **Test evidence:** no evidence, incomplete, failing or local tests passed. Missing, skipped and expected-failing tests never count as passes. Failing subtests remain failures.
- **Qualification:** unqualified. The runner deliberately cannot grant release qualification. A unit test with mocks cannot establish behavior across actual applications, desktop servers or architectures.

Most catalog cases currently have no mapped evidence. Existing live suites provide additional observations but have not yet been exhaustively linked to the catalog. Neither an unmapped requirement nor a passing assertion proves the entire feature missing or complete. Read acceptance criteria and mapping limits together. The catalog remains the authoritative list; unknown IDs in the map fail validation.

## Isolated X11 integration

Install the dependencies listed in `.github/workflows/tests.yml`, then run:

```sh
LUDA_ISOLATED_TEST_DISPLAY=1 xvfb-run -a -s '-screen 0 1440x900x24 -nolisten tcp' dbus-run-session -- .venv/bin/python scripts/headless_tests.py
```

The runner creates a separate display and D-Bus session, starts its own XFWM4, and exercises the native and real MCP suites against their owned GTK fixtures. Individual suites have a 120-second watchdog. Logs and outcomes are retained on failure. This does not use or modify the human's KasmVNC desktop. Shared `:1` tests must still hold `/tmp/luda-live-tests.lock` for their whole lifetime as required by `AGENTS.md`.

CI runs unit contracts and the isolated desktop job on Ubuntu 24.04 AMD64. A configured workflow is not evidence of a successful hosted CI run. The local environment is ARM64; inspect the actual artifact environment before interpreting results.

## Remaining release evidence

Fresh microsandbox provisioning, a clean Mac-to-Codex SSH onboarding session, KasmVNC-specific reconnects, repeated held-out workflows, distribution/toolkit/display matrices, human-input interference, rich clipboard formats and protected credential workflows require separate evidence. Headless GTK fixtures do not replace these. Failure transcripts and independent file/DOM/application oracles are required for actual application claims; fixture text is synthetic and should never contain user data.
