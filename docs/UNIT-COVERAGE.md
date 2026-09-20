# Historical unit mapping coverage snapshot

This is the historical 489-test snapshot. See [the later 551-test mapping audit](../tests/evidence/historical-reports/UNIT-COVERAGE-CURRENT.md) for the newer scoped inventory.

Generated from `docs/requirements.json`, `docs/test-map.json`, actual unittest discovery and the local qualification report on the `f506037` runtime snapshot plus this mapping update. This is a mapping audit, not release qualification.

- Catalog: 346 cases (296 P0, 30 P1, 20 P2).
- Mapped: 118 requirements reference 186 distinct unit methods.
- Discovered and executed: 489 unit methods; all passed. Every mapped test ID exists in actual discovery.
- Requirement evidence: 118 local-tests-passed; 228 without mapped evidence. All 346 remain release-unqualified.

| Area | Mapping change | Evidence boundary |
|---|---|---|
| OBS-11 | Eight sampled font diagnostics, failures, cancellation and advisory readiness | Private Pango live test is separate; no universal glyph or app typography claim. |
| OBS-08 | Valid black capture versus missing/corrupt/truncated image | Synthetic capture payloads; no inferred application health. |
| KEY-09 | Repeat count rejection and native plan propagation | Bounded request contract; live delivery is separate. |
| SEM-09 | Complete bounded name identity and protected-name refusal | Mock provider stale-handle checks; not every toolkit race. |
| DATA-01/02/03, SEM-05 | Current TableCell identity, replace/add and provider no-op | No automatic virtualized scrolling/reacquisition or range selection guarantee. |

Reproduce unit evidence with `.venv/bin/python scripts/qualify.py`; it records exact source hashes, revision and environment in the generated artifact. Historical live results must retain their original source/environment association. Counts describe this snapshot and should be refreshed when the map changes.
