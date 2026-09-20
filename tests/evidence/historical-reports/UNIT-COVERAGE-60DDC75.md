# Unit mapping coverage: 745-test snapshot

Source `60ddc75` passed 745 root tests. The matching ordinary-account run passed 737, with eight unavailable Codex CLI tests explicitly skipped. Both retained unchanged fingerprint `a39e99733300010e9ab71b2dedfd07faa8ac77e647b5e0f5baf071751c6f01e9`. Records are `root-managed-boundaries-final.json` and `ordinary-managed-boundaries.json` under `artifacts/qualification/backend-host/`.

- Catalog: 346 cases, all release-unqualified.
- Mapping: 145 requirements and 339 distinct exact unit methods.
- Evidence: 145 local-tests-passed; 201 cases without mapped unit assertions.

The [730-test snapshot](UNIT-COVERAGE-F6A0230.md) retains hosted browser, media and Silo evidence. Subsequent tests cover optional managed browser configuration, revalidation and release membership, plus native browser insertion/deletion at grapheme boundaries. A passing refusal is evidence of preventing an unsupported edit, not support for arbitrary Unicode range editing.

Actual private MCP boundary run `1789891304330310696` passed in 15.927 seconds, including unchanged combining/emoji deletion refusals and whole-field replacement. Independent review reproduced the original destructive partial-emoji deletion and confirmed its correction. The separate explicit clipboard prototype passed 25 rich range cases, while its native comparison failures remain recorded; clipboard transport is still test-only at this snapshot.

All seventeen Silo patches checked and applied to a fresh pinned checkout; embedded skill bytes match and 25 Silo integration/CI checks passed. Actual Mac packaging, Silo deployment and fresh VM acceptance remain outstanding.

Managed installation was exercised through a real wheel and ordinary-account launcher at earlier source `737e670`, with 46 installed runtime modules byte-equal to source, actual Unicode/LF browser edits and confirmed EOF cleanup. A later stricter installed-module-set check found stale `build/lib` content included in a wheel; that failed run is retained and requires an installer correction. No passing hosted managed-installation result is claimed here.
