# HTML suite scope-contract correction

The integrated run at aef930b failed its old assertion that frame presence makes desktop_inspect return BROWSER_SCOPE_UNSUPPORTED. The intentionally changed read-only contract now keeps independently mapped native AX controls and explicitly reports owned-provider unavailability. Original matrix and failing suite log are retained unchanged in compressed form; other seven suites passed.

The corrected check requires real native nodes, the same window, empty owned text_fields and the exact owned-provider unavailable code. Cached owned read and type must still refuse with effect none; fresh independent application text, selection, input events and document generation must remain unchanged. This does not add frame DOM support or an input fallback. The full HTML/lifecycle suite must run again to qualify the corrected assertion.

The corrected full HTML/lifecycle suite passed all 42 records in 17.953 seconds at source c73cb56, unchanged fingerprint e6dafc23336db10201ab789946df0763e246b00a6fdfd7dd525e5a1446a71389. Final matrix run-1789900556052411107 and complete cases/log are retained separately.
