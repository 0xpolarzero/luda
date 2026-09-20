# Unit mapping coverage: 704-test snapshot

Source `dc4dc70` passed 704 root unit tests. The matching ordinary-account run passed 696 and explicitly skipped eight Codex CLI tests unavailable to that account. Both retained unchanged full source fingerprint `0bd219a9b115df780d47af2c8dcdb5967d966874f8d18ef064a5d7f736f56fbf`. The ordinary record has no Git revision metadata, but its matching fingerprint identifies the tested files.

- Catalog: 346 cases; all remain release-unqualified.
- Mapping: 138 requirements and 318 distinct exact unit methods.
- Evidence: 138 local-tests-passed; 208 cases without mapped unit assertions.
- Records: `artifacts/qualification/backend-host/root-recovery-storage.json` and `ordinary-recovery-storage.json`.

The [688-test snapshot](UNIT-COVERAGE-ED4EDCB.md) retains earlier recording evidence and the initial output-directory failure. Eleven matching tests and five input-storage tests followed. The intermediate root matching run passed 699 tests at `503dd73`; the integrated private image-matching and OCR suites also passed with unchanged source (`run-1789886426751883661`). Actual shared KasmVNC MCP passed 23 checks at `dc4dc70` under the desktop lease.

Hosted [optional media](https://github.com/0xpolarzero/luda/actions/runs/35494867997) passed OCR, image matching, recording and recording faults at `503dd73`, with unchanged fingerprint `362708ac1803310e328221659070dbda9b997b27b3b22d980b031834f522be36`. The suite durations were 12.405, 20.176, 6.199 and 13.062 seconds. [Codex registration](https://github.com/0xpolarzero/luda/actions/runs/35494868032) and [native applications](https://github.com/0xpolarzero/luda/actions/runs/35494868014) passed at that revision too. These precede the shared helper storage correction and structured rectangle schema.

A [fresh-agent media workflow](../tests/evidence/media-usability/README.md) found a rectangle-schema discoverability gap. The subsequent correction at `2b49b4f` passed six protocol tests and the six-case live matching suite. That targeted result is separate from the 704-test snapshot; its newly added test is not silently included in this total.

All thirteen ordered Silo patches were checked and applied to a fresh pinned checkout at `237b8e7`; embedded skill bytes matched and 23 integration unit tests passed. Native recovery tests and their actual CLI scope are documented in [the integration](../integrations/silo/README.md). No Linux result establishes Mac/Silo acceptance.

Run `.venv/bin/python scripts/qualify.py --output /absolute/evidence.json` for a new exact-source record. Unit assertions, live fixture association, application qualification and fresh product integration remain separate claims.
