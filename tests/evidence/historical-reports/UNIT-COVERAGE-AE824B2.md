# Unit mapping coverage: 645-test snapshot

This scoped audit uses source snapshot `ae824b2` and its immutable unit evidence (`artifacts/qualification/silo-final/root-unit-corrected.json`). It preserves the [earlier 489-test snapshot](UNIT-COVERAGE.md) as historical evidence. Counts are not release qualification.

- Catalog: 346 cases (296 P0, 30 P1, 20 P2); all remain release-unqualified.
- Mapped: 133 requirements, 281 distinct exact unit IDs.
- Actual root discovery/execution: 645 tests, all passed; every mapped test exists.
- Same-source UID 1001 run: 644 passed, one Codex CLI registration test explicitly skipped because the CLI was unavailable to that account.
- Evidence statuses: 133 local-tests-passed; 213 cases without mapped unit evidence.

| Cases | Added evidence | Limit |
|---|---|---|
| AUTH-09 | Selected-session lock/screensaver mutation preflight, timeout, observation/recovery access | Unknown/inactive is not unlocked; no atomic input/lock guarantee. |
| ENV-08, SEM-09 | Authenticated bus generation and scoped provider identities | No automatic bridge reconnection or universal session-outage recovery. |
| LIFE-06 | Backend swap and closed-cache invalidation | Does not stand in for full MCP process/client restart qualification. |
| SEM-05, SEM-09, DATA-01/02/03 | Fresh combo/list/table identities and exact retained selections | Bounded selected-row anchors; no automatic virtualized scrolling or range semantics. |
| WIN-04 | Original full generation in activation readback | Numeric asynchronous window-manager dispatch still has an identity race. |
| SEC-07, ERR-08 | Unexpected exception redaction and uncertain effects; recovery-owner preservation | Typed diagnostic producers and external application logs need their own safeguards. |

Run `.venv/bin/python scripts/qualify.py` to regenerate unit evidence for the exact current checkout. The recorded run reports source unchanged during execution and stores source hashes/environment at the requested output path (default `artifacts/qualification/unit.json`). Mapped assertions remain narrower than their full acceptance criteria; historical live application results retain their own runtime/environment association.

The matching ordinary-account record is `artifacts/qualification/silo-final/ordinary-unit-corrected.json`. Both runs retained unchanged source fingerprint `7d435e78e00e7a8af4560c3f62c07869058f9d5ff5f8675411c1f041d2b7f689`. The ordinary account has no Git revision because of checkout ownership; matching full hashes bind it to the root revision. An initial pair at `ffd10f5` failed the generated live-inventory freshness assertion after adding the standalone Silo composition fixture. Those original results remain in the adjacent `root-unit.json`/`ordinary-unit.json`; regenerating the inventory corrected the failure.

DIAG-10 and SHIP-08 now have mapped report privacy, code/verb projection and installed/editable identity contracts. Twenty-one additional Silo-wrapper tests cover its source, metadata and lifecycle boundaries; they are not silently mapped to broad fresh-VM acceptance. Live source-checkout MCP passed 23 checks at the same source in `run-1789881029369465377`. See [the integration assets](../integrations/silo/README.md) for separate Rust/frontend checks and [actual HTTPS/bootstrap composition](SILO-COMPOSITION-QUALIFICATION.md) for its provisioning exclusions.
