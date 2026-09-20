# Sanitized bug reports

Call `desktop_report` through the connected MCP server to collect diagnostics for a bug. It returns JSON and does not save or upload a report, take screenshots, collect reproduction prose, or replay actions. The read-only doctor probe can run while input is paused. If diagnostics are unavailable, fields are null rather than raw error messages.

For an installed guest, `luda report` prints the same schema to stdout. Run it in the selected desktop account/session using the installed launcher, for example:

```sh
/opt/luda/current/.venv/bin/luda-session --user silo-desktop -- /opt/luda/current/.venv/bin/luda report
```

The CLI is a fresh process: `history_scope` is `fresh_cli_process` and its operations array is empty. It cannot recover the connected MCP server's earlier operations. Use the MCP tool when those outcomes matter.

Schema version 1 contains:

- Fixed distribution ID/version, architecture, Python version and fixed Python/native dependency package versions. Unknown formats or unavailable packages are null. Native package versions currently use bounded Debian package-manager diagnostics; other distributions can report nulls.
- Strict boolean health projections for display, topology, accessibility, session bus, fixed executables, keyboard availability, control availability/pause, and session input readiness. These are a point-in-time probe, not application success or permission to resume.
- `recovering` and at most 32 recent operations from this MCP process, captured before the report's doctor probe. Allowed fields are operation ID, fixed backend method name, effect, elapsed milliseconds and success boolean. Semantic action arguments are omitted; `element` does not identify which semantic action ran. Empty/malformed metadata is omitted. There is no persistent history.
- Explicit omitted-context and limitation lists. `effect` is `none`: generating a report performs no desktop input.

The projection excludes screenshots, window/control titles, input and protected text, clipboard contents, filesystem paths, environment variables, exception messages/details, arbitrary diagnostic fields, action arguments, and reproduction steps. Version and architecture metadata still describe the installation; this is a content-minimized report, not an anonymity guarantee. Diagnostic failures cannot add their exception text to the export. Null health during busy/recovery conditions is not evidence that the desktop is unhealthy.

When reporting a bug, provide a separate minimal synthetic reproduction: the intended action, synthetic application/fixture setup, relevant operation ID and observed outcome. Do not silently retain or attach private documents, credentials, screenshots or raw doctor output as reproduction context. A caller can explicitly save the returned JSON, or redirect CLI stdout to a chosen file, then explicitly share or delete that file. Luda creates no report archive and has no automatic retention, upload, deletion or replay mechanism.

`tests/test_report.py` covers injected sensitive fields, malformed metadata, bounded history, diagnostic exceptions, public read-only schema and an actual fresh CLI invocation without desktop environment variables. These tests do not qualify a fresh Mac/SSH installation or every provider's diagnostics.

## Live integration evidence

At `bfa9440`, the full unit suite passed 621 tests as root and 620 with one
explicit unavailable-Codex-CLI skip as UID 1001. Both evidence records have
unchanged identical source fingerprint `2387d33d303df00535fc5f3bea773bab3d14d45429f2fec004aba9155a849559`.
The ordinary-account first attempt passed its tests but could not write its
report to a root-owned output directory; that failed runner log is retained.
Repeating with an owned output directory produced the complete evidence record.

Actual stdio MCP passed all 22 checks on both a private Xvfb desktop
(`run-1789879878542042287`) and the selected KasmVNC desktop under the shared
desktop lease (`artifacts/report-identity/bfa9440-kasm/`). The report correlated
the prior paste operation, excluded the synthetic text, control name, checkout
path and target IDs, returned only JSON, reported ready health, and left
independently persisted widget text unchanged. Doctor’s tool-schema fingerprint
matched canonical actual `tools/list` declarations. This tests the source checkout
in the guest, not a new installed release or Mac SSH discovery.
