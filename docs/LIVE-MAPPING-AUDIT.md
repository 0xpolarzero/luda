# Live-suite association audit

The matrix associations were checked against the actual acceptance catalog and each registered fixture's source. They describe related assertions and limitations, not complete implementations, passing results or release qualification. This audit changes metadata only. Existing raw run artifacts retain their original labels, source hashes and outcomes; corrected labels do not retroactively qualify those runs.

| Suite | Correction and reason |
|---|---|
| bus-generation | Remove large-tree AX-06 and ambiguous restart LIFE-06; use missing/broken bus ENV-08/FAULT-04, server-handle STATE-02 and target-identity SEM-09. |
| injector-reuse | Remove invalid-chord KEY-07 and uninstall LIFE-04. Owned injector disconnect and killed-helper release concern KEY-08 and worker cleanup LIFE-05. |
| mcp-input-recovery | Remove invalid-chord KEY-07 and two-client CONC-01. Explicit cleanup, pause preservation and replacement-server tests concern KEY-08, ERR-09, STATE-02, CONC-05 and FAULT-05. |
| semantic | Add the actual choice and replace/add selection coverage under SEM-05 and DATA-03. |
| accessibility-lifecycle | Replace generic server restart LIFE-06 with actual accessibility-bus failure FAULT-04; retain real XFCE lifecycle associations. |
| x11-isolation | Frozen/killed private X helpers concern FAULT-05 and bounded backend failure ERR-06, not VM shutdown or complete desktop reconnect qualification. |
| window-metadata | Its ten windows have distinct titles; remove duplicate-title WIN-01. Preserve bounded metadata PERF-07 and add measured frame geometry GEO-01 and malformed metadata ERR-06. |
| clipboard-interference | Add independently tested PRIMARY preservation CLIP-01, actual clipboard manager CLIP-06, competing controllers CONC-10 and owner replacement FAULT-08. |
| application-launch | The fixture checks account identity, literal arguments, dispatched status and bounded launch return (SEC-01/03, ERR-02, PERF-05). It is not an SSH attach test or a GTK editor save/reopen workflow. |
| application-services | D-Bus/terminal launch acceptance and timeout handling concern ERR-02/04; no SSH attachment occurs. |

The remaining matrix associations were retained after comparison with fixture scope. Some intentionally associate a failing or unsupported case, including browser rich text, Electron non-BMP replacement, protected Firefox input and IME composition. An association therefore cannot be counted as a pass. Application launch/discovery has no dedicated exhaustive acceptance family in the current catalog; these narrow error/security associations do not pretend to supply one.
