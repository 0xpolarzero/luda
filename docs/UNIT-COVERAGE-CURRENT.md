# Unit mapping coverage: 602-test snapshot

This scoped audit uses source snapshot `e7fea80` and its immutable unit evidence (`artifacts/qualification/bootstrap-cleanup-unit.json`). It preserves the [earlier 489-test snapshot](UNIT-COVERAGE.md) as historical evidence. Counts are not release qualification.

- Catalog: 346 cases (296 P0, 30 P1, 20 P2); all remain release-unqualified.
- Mapped: 131 requirements, 264 distinct exact unit IDs.
- Actual discovery/execution: 602 tests, all passed; every mapped test exists.
- Evidence statuses: 131 local-tests-passed; 215 cases without mapped unit evidence.

| Cases | Added evidence | Limit |
|---|---|---|
| AUTH-09 | Selected-session lock/screensaver mutation preflight, timeout, observation/recovery access | Unknown/inactive is not unlocked; no atomic input/lock guarantee. |
| ENV-08, SEM-09 | Authenticated bus generation and scoped provider identities | No automatic bridge reconnection or universal session-outage recovery. |
| LIFE-06 | Backend swap and closed-cache invalidation | Does not stand in for full MCP process/client restart qualification. |
| SEM-05, SEM-09, DATA-01/02/03 | Fresh combo/list/table identities and exact retained selections | Bounded selected-row anchors; no automatic virtualized scrolling or range semantics. |
| WIN-04 | Original full generation in activation readback | Numeric asynchronous window-manager dispatch still has an identity race. |
| SEC-07, ERR-08 | Unexpected exception redaction and uncertain effects; recovery-owner preservation | Typed diagnostic producers and external application logs need their own safeguards. |

Run `.venv/bin/python scripts/qualify.py` to regenerate unit evidence for the exact current checkout. The recorded run reports source unchanged during execution and stores source hashes/environment at the requested output path (default `artifacts/qualification/unit.json`). Mapped assertions remain narrower than their full acceptance criteria; historical live application results retain their own runtime/environment association.
