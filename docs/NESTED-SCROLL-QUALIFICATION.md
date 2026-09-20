# Nested scrolling panes

`tests/live_nested_scroll.py` drives a real GTK3 nested scrolling fixture through
one actual stdio MCP connection. It finds each pane in public accessibility,
observes a fresh screenshot, converts the observed native bounds into returned
image coordinates and sends one explicit wheel action. Toolkit adjustment values
are persisted separately by the application as the independent oracle.

Run as an ordinary user:

```sh
.venv/bin/python scripts/qualification_matrix.py --suites nested-scroll
```

The first ARM64/UID1001 private-display run passed three checks in 4.096 seconds:

- Inner vertical scrolling changed only the inner vertical adjustment (0→102.60).
- Inner horizontal scrolling changed only the inner horizontal adjustment (0→151.82).
- Vertical scrolling outside the inner pane changed only the outer vertical adjustment (0→176.17).

Each check waits for the expected application change and then observes a 250ms
quiet period without retrying input. The other two adjustments must remain
unchanged. Luda reports dispatch, not an application-independent assertion that
some particular pane moved; the test establishes the effect through GTK state.

Evidence is `artifacts/qualification-matrix/run-1789873942595511581`, unchanged
source fingerprint `1d7bb5442a6b387eff54165d43e231d889f69594c54bd491cbfd45c3f44d0053`,
with no owned process survivors. This is scoped evidence for PTR-05, not a claim
about every toolkit, touchpad gesture, scroll chaining at boundaries or kinetic
animation. Catalog qualification remains unchanged.
