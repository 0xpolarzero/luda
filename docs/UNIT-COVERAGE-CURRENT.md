# Unit mapping coverage: 717-test snapshot

Source `042c137` passed 717 root unit tests. The matching ordinary-account run passed 709 and explicitly skipped eight Codex CLI tests unavailable to that account. Both retained unchanged full source fingerprint `d99a03ac42fa7a623c2db1c705e5cb0e3c8c71f15313de8ec0a22f3dba43898c`.

- Catalog: 346 cases; all remain release-unqualified.
- Mapping: 138 requirements and 318 distinct exact unit methods.
- Evidence: 138 local-tests-passed; 208 cases without mapped unit assertions.
- Records: `artifacts/qualification/backend-host/root-owned-browser.json` and `ordinary-owned-browser.json`.

The [704-test snapshot](UNIT-COVERAGE-DC4DC70.md) preserves earlier media, storage, live MCP and fresh-agent evidence. This snapshot adds the structured rectangle-schema test and twelve optional owned-browser checks.

The integrated [owned-browser](OWNED-BROWSER.md) suite passed through actual MCP on an ordinary-account private Xvfb desktop in 10.906 seconds, including native composition refusal and cleanup faults. Record `run-1789888137937772227` retained unchanged source. Independent review separately reproduced and verified fixes for stopped-guardian cleanup and profile-directory replacement. These checks establish the named HTML input/textarea behavior, not general rich-editor compatibility.

All fifteen ordered Silo patches checked and applied to a fresh pinned checkout; embedded skill bytes matched and 23 integration unit tests passed. The responsive panel separately passed ten Chromium layout cases plus keyboard/focus checks, 30 frontend tests and TypeScript checking. Native recovery evidence and actual CLI scope are documented in [the integration](../integrations/silo/README.md). No Linux result establishes Mac/Silo acceptance.

All four hosted workflows passed at the preceding `5951e5b`: [desktop contracts](https://github.com/0xpolarzero/luda/actions/runs/35495533003), [native applications](https://github.com/0xpolarzero/luda/actions/runs/35495533010), [Codex registration](https://github.com/0xpolarzero/luda/actions/runs/35495533018), and [optional media](https://github.com/0xpolarzero/luda/actions/runs/35495533042). Those runs precede the owned-browser integration.

Run `.venv/bin/python scripts/qualify.py --output /absolute/evidence.json` for a new exact-source record. Unit assertions, live fixture association, application qualification and fresh product integration remain separate claims.
