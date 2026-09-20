# Unit mapping coverage: 661-test snapshot

This record binds source `44f53ea` to unchanged fingerprint `bc52bf85d23b2c8d794d75f9448e76346180806e01d5e49e2162fbec98889c65`. The [645-test snapshot](UNIT-COVERAGE-AE824B2.md) remains available with its original results and failures. Counts are evidence, not release qualification.

- Catalog: 346 cases (296 P0, 30 P1, 20 P2); all remain release-unqualified.
- Mapping: 135 requirements and 287 distinct exact unit methods.
- Root: 661 tests passed; every mapped test exists.
- Same-source UID 1001: 655 passed, six Codex CLI tests skipped because that account cannot discover the CLI.
- Requirement evidence: 135 local-tests-passed; 211 without mapped unit assertions.

Exact records are `artifacts/qualification/backend-host/root-session-fix.json` and `ordinary-session-fix.json`. Both report the same unchanged full source fingerprint. The ordinary account has no Git revision because of checkout ownership; the full hash binds it to the root snapshot. Earlier 658-test records in the same directory remain intact.

New assertions cover explicit unsupported Wayland/Xwayland refusal, a native X11 target with unrelated Wayland hints, host plugin remote-shell quoting, two distinct VM MCP namespaces, actual temporary-profile Codex registration and partial-result reconciliation, plus launcher working-directory selection after privilege drop. Host registration tests do not establish a real SSH connection or Mac Silo onboarding.

At `6c2e18d`, 12 of 16 ordinary-user headless suites passed. Four failed on reused root-owned fixture artifacts, including an unavailable independent state oracle; these failures are retained in `artifacts/headless/results.json`. Fresh artifact paths and explicit suite selection were added in `47b76e9`; all four affected suites then passed in `artifacts/headless/run-1789882459451378517/` with unchanged source fingerprint `8ffadfb209f66c36867c2b567f3a72f8b779006bff9026115af8eaa3329373c3`. This is a corrected four-suite run, not a second full run. Actual KasmVNC MCP also passed 23 checks at that source while holding the shared desktop lease.

Hosted AMD64 [Desktop contracts](https://github.com/0xpolarzero/luda/actions/runs/35491955624) and [Native application workflows](https://github.com/0xpolarzero/luda/actions/runs/35491955619) both passed at `6c2e18d`. Those hosted results precede the artifact-isolation and launcher-cwd changes.

Run `.venv/bin/python scripts/qualify.py --output /absolute/evidence.json` for a new exact-source record. Unit mapping, live fixture association, application qualification and fresh product integration remain separate claims.
