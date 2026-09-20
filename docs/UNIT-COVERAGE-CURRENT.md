# Unit mapping coverage: 688-test snapshot

Source `ed4edcb` passed 688 root unit tests. The matching ordinary-account run passed 680 and explicitly skipped eight Codex CLI tests unavailable to that account. Both retained unchanged full source fingerprint `1735e8dc9c35c5b9e6e10e00ede1bff50a7fd656c177257c7594f9ef454e9bd2`. The ordinary account could not read Git revision metadata; its matching file fingerprint establishes the source identity.

- Catalog: 346 cases; all remain release-unqualified.
- Mapping: 137 requirements and 307 distinct exact unit methods.
- Evidence: 137 local-tests-passed; 209 cases without mapped unit assertions.
- Records: `artifacts/qualification/backend-host/root-recording.json` and `ordinary-recording.json`.

The [679-test snapshot](UNIT-COVERAGE-0217541.md) preserves earlier OCR, host registration, hosted results and retained failures. The subsequent root run at `fb100ec` also passed 679 tests (`root-native-eight.json`).

Nine new tests cover temporary recording bounds, storage and startup failures, safe artifact deletion, parent-death setup, malformed metadata cleanup and cleanup availability while ordinary input is blocked. The embedded Silo skill now matches through patch ten; the agent branch's earlier mismatch remains recorded in [recording evidence](RECORDING.md).

At the same `ed4edcb` fingerprint, private ordinary-account recording and recording-faults suites passed in 4.288 and 10.088 seconds (`artifacts/qualification-matrix/run-1789885682806247265/`). They verify nine scoped live assertions, including independently decoded rendered frames and owner-death cleanup. The initial integrated run `run-1789885638299969327` failed before starting because the root-owned artifact parent lacked ordinary-writable recording subdirectories. That fixture failure is retained; creating only those new output directories preceded the passing rerun.

Run `.venv/bin/python scripts/qualify.py --output /absolute/evidence.json` for a new exact-source record. Unit assertions, live fixture association, application qualification and fresh product integration remain separate claims.
