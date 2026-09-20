# Provider text contract review

This review targets false-success risks in bounded text readback and offset conversion. It does not expand GTK4 window-coordinate trust or remove known provider failures.

## Reproduced faults and corrections

Five deterministic regression checks in `tests/test_provider_snapshots.py` cover:

- A provider grows between its character-count query and bounded text query. Previously the requested old-length prefix could be reported as complete. Luda now rechecks the native count after reading and reports `TEXT_CHANGED` if it differs.
- A provider grows immediately after a native replacement. The formerly accepted `new` prefix of actual `newsuffix` must never verify the replacement. The resulting error reports `effect=uncertain` because input was already dispatched.
- Public readback previously refreshed the underlying text three times while retaining a length from an earlier refresh. Text, character count, and truncation now derive from one bounded snapshot.
- A Qt provider reporting a code-point count for non-BMP text conflicts with its declared UTF-16 contract. Luda now rejects that inconsistency instead of forcing an incorrect mapping. Ordinary ASCII remains unambiguous and uses the known Qt convention.
- A failed snapshot before mutation reports `effect=none`; after mutation it reports `effect=uncertain`. Native error contents do not enter the diagnostic.

The first three tests failed against the prior implementation before the corrections. This is fault-injection evidence, not a claim that every real provider exhibits those timing faults. Character-count checks cannot make an application expose an atomic snapshot: a same-length concurrent edit or a change after observation can still occur. Input transactions continue to verify their observed destination independently and must not blindly retry uncertain results.

## Independent application regression

The ordinary-UID private-session matrix ran `semantic`, `toolkits`, and `firefox` on 2026-09-20. Source hash `ae8846882a1377f2607bd9848eea029e627f3742b52cba87c4f805b08b523815` remained unchanged before/after. All three process cleanups recorded no survivors.

| Suite | Outcome |
|---|---|
| GTK3 semantic | Passed, 6.093 s |
| Qt | All 29 recorded cases supported against independent fixture state |
| GTK4 | 21 supported; 3 provider errors, 3 dependent blocked cases, 2 unsupported checkbox checks |
| Firefox 156.0 | 14/15 checks passed; explicit protected input remains unsupported |

The combined toolkit suite and Firefox suite therefore still exit nonzero. GTK4 errors are selection creation, caret-zero movement, and astral selection; dependent inserts are not attempted. Its checkbox exposes no recognized state-changing action. These are unchanged capability gaps, not converted into passes.

GTK4's unique-title-and-size mapping still requires a unique top-level candidate within the scoped PID; its coordinates remain unavailable for pointer input. This review found no evidence justifying weaker identity matching or generic keyboard emulation for those missing semantic operations. Qt's real UTF-16 behavior continues to pass its existing Unicode, selection, insertion, protected-field, value and modal fixture checks.
