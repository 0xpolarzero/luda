# Native IME observation evidence

See `docs/NATIVE-IME-FEASIBILITY.md`. Each directory retains the original matrix report (including per-file source hashes), raw observations and suite output compressed with deterministic gzip headers. All text is synthetic fixture data. No upstream source files are vendored; `primary-sources.json` records the pinned source downloads inspected during the audit.

- `1789900481579259530`: original late-listener timing probe; listener attached during incoming digits, so it received subsequent events. This is not a valid already-quiescent attach-gap test.
- `1789900581777806203`: explicit 250ms unchanged event-generation precondition before listener attachment; actual D-Bus introspection added. Four late listeners remain unknown, while early listeners report pending composition.
- `1789900684931593002`: additionally records GTK3 app-supplied accessible IDs versus installed GTK4 empty IDs. Four pending compositions preserved; repeated external reads remain unchanged; no owned-process survivors.

Passing exit codes describe completion of read-only observations, not passing EDIT-10 input protection. No conflicting input is attempted after the pending-state precondition. Existing failing destructive-conflict probes remain independent evidence.
