# Unit mapping coverage: 730-test snapshot

Source `f6a0230` passed 730 root tests. The matching ordinary-account run passed 722, with eight unavailable Codex CLI tests explicitly skipped. Both retained unchanged fingerprint `81d3f139a5a377e7fd2e0f1149e4cd9630dd0a424bb5ffc007bf8031f0ba373e`. Records are `root-browser-mapped.json` and `ordinary-browser-mapped.json` under `artifacts/qualification/backend-host/`.

- Catalog: 346 cases, all release-unqualified.
- Mapping at this source: 145 requirements and 339 distinct exact unit methods.
- Evidence: 145 local-tests-passed; 201 cases without mapped unit assertions.

The [719-test snapshot](UNIT-COVERAGE-F98B139.md) retains browser lifecycle, matching source hashes, hosted AMD64 browser and actual Silo registration results. Eleven subsequent tests cover the [cooperating paragraph provider](../integrations/prosemirror/README.md), including selection-time content changes, unsupported stored marks, and known paragraph limits.

At the preceding source `0af1a74`, integrated actual MCP run `run-1789889430917405927` passed with unchanged source: ordinary HTML/browser cleanup in 11.467 seconds and cooperating rich-editor workflows in 22.952 seconds. Rich evidence includes exact text/paragraph structure, preserved existing formatting, explicit new formatting readback, composition refusal, actual cancellation and no replay. Independent review reproduced two defects and verified their corrections before integration. Generic rich editors, arbitrary schemas and middle selections remain unsupported.

All sixteen Silo patches checked and applied to a fresh pinned checkout; embedded skill bytes match and 23 integration unit tests passed. Actual Mac packaging, Silo deployment and fresh VM acceptance remain separate outstanding work.

The live inventory contains 78 fixture scripts and 162 distinct requirement associations. These counts are not qualification percentages. Run `.venv/bin/python scripts/qualify.py --output /absolute/evidence.json` for a new exact-source record.

Hosted source `0af1a74` also passed [HTML and paragraph browser suites](https://github.com/0xpolarzero/luda/actions/runs/35497076130) in 34.409 and 57.376 seconds and [all four optional media suites](https://github.com/0xpolarzero/luda/actions/runs/35497076155), including corrected image matching in 22.936 seconds. Both retained fingerprint `0d7cc02ca44804364b26ed0aad3a0f2f526d251622b0c03047062784f43b827e`, matching the prior local records. The later map adds only named browser assertions with explicit provider limits; no release qualification changes.
