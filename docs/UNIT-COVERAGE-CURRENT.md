# Unit mapping coverage: 679-test snapshot

Source `0217541` passed 679 root unit tests. The matching ordinary-account run passed 671 and explicitly skipped eight Codex CLI tests because the CLI was unavailable to that account. Both retained unchanged full source fingerprint `0684d83d005067881ba36143aa367179064a332c00a243b9cb75b22e5b77922c`.

- Catalog: 346 cases; all remain release-unqualified.
- Mapping: 136 requirements and 298 distinct exact unit methods.
- Evidence: 136 local-tests-passed; 210 cases without mapped unit assertions.
- Records: `artifacts/qualification/backend-host/root-ocr-final.json` and `ordinary-ocr-final.json`.

The [661-test snapshot](UNIT-COVERAGE-44F53EA.md) preserves earlier results and the headless fixture-permission failures. An intermediate ordinary-account run (`ordinary-ocr-integrated.json`) encountered an unresolved generated-inventory merge conflict and failed that freshness check. It remains retained; regenerating the inventory and completing the merge preceded both passing final runs. No failure was converted into a pass.

New evidence includes the optional screenshot OCR parser, limits, actual child cancellation, cache bounds and read-only protocol; complete effective host transport validation; malformed bundle JSON refusal; source-dependency filtering; and ordered Silo patch/skill checks. The browser prototypes are separate live evidence, with their actual failures preserved, rather than production support inferred from asset tests.

At source `9bf509b`, the integrated OCR matrix run `run-1789883951540941145` passed in 2.425 seconds with unchanged fingerprint `f9b3ef0cbd883698fd42aa918f08d4f9d176d2cb228ce40405a2dc9686af9932` and no surviving owned processes. Actual KasmVNC MCP passed 23 checks while holding the shared desktop lease. After giving each MCP fixture a fresh oracle directory, another 23-check run passed at `9e366e7`, retained under `artifacts/mcp/run-1789884289739842557/`.

Hosted [Codex registration](https://github.com/0xpolarzero/luda/actions/runs/35492837259), [desktop contracts](https://github.com/0xpolarzero/luda/actions/runs/35492837266) and [native application workflows](https://github.com/0xpolarzero/luda/actions/runs/35492837275) passed on AMD64 at `f7a8720`. The new Codex job installs the integrity-locked 0.155.1 CLI and fails on skipped tests. These hosted results precede OCR. The earlier native run at `2c7e362` failed waiting for Mousepad's automatic focus; its artifact is retained. Explicitly activating the sole owned window fixed the fixture assumption; the local affected workflow and subsequent hosted native run passed.

Run `.venv/bin/python scripts/qualify.py --output /absolute/evidence.json` for a new exact-source record. Unit assertions, live fixture association, application qualification and fresh product integration remain separate claims.
