# Sanitized bug reports

Call `desktop_report` through the connected MCP server to collect diagnostics for a bug. It returns JSON and does not save or upload a report, take screenshots, collect reproduction prose, or replay actions. The read-only doctor probe can run while input is paused. If diagnostics are unavailable, fields are null rather than raw error messages.

For an installed guest, `luda report` prints the same schema to stdout. Run it in the selected desktop account/session using the installed launcher, for example:

```sh
/opt/luda/current/.venv/bin/luda-session --user desktop -- /opt/luda/current/.venv/bin/luda report
```

The CLI is a fresh process: `history_scope` is `fresh_cli_process` and its operations array is empty. It cannot recover the connected MCP server's earlier operations. Use the MCP tool when those outcomes matter.

Schema version 1 contains:

- Fixed distribution ID/version, architecture, Python version and fixed Python/native dependency package versions. Unknown formats or unavailable packages are null. Native package versions currently use bounded Debian package-manager diagnostics; other distributions can report nulls.
- Validated SHA-256 identities from the existing public doctor for complete tool declarations and the server-bundled skill, plus its fixed availability status. These identify installation artifacts, not which skill an agent loaded; unavailable identities are null.
- Strict boolean health projections for display, topology, accessibility, session bus, fixed executables, keyboard availability, control availability/pause, and session input readiness. These are a point-in-time probe, not application success or permission to resume.
- `recovering` and at most 32 recent operations from this MCP process, captured before the report's doctor probe. Allowed fields are operation ID, fixed backend method name, effect, elapsed milliseconds, success boolean, recognized fixed error code and semantic verb for `element` operations (read/secret/choose/focus/invoke/select/value/check/expand). Unknown codes and verbs are omitted. The caller-supplied native invoke action/name and all other action arguments are omitted. Empty/malformed metadata is omitted. There is no persistent history.
- Explicit omitted-context and limitation lists. `effect` is `none`: generating a report performs no desktop input.

The projection excludes screenshots, window/control titles, input and protected text, clipboard contents, filesystem paths, environment variables, exception messages/details, arbitrary diagnostic fields, action arguments, and reproduction steps. Version and architecture metadata still describe the installation; this is a content-minimized report, not an anonymity guarantee. Diagnostic failures cannot add their exception text to the export. Null health during busy/recovery conditions is not evidence that the desktop is unhealthy.

When reporting a bug, provide a separate minimal synthetic reproduction: the intended action, synthetic application/fixture setup, relevant operation ID and observed outcome. Do not silently retain or attach private documents, credentials, screenshots or raw doctor output as reproduction context. A caller can explicitly save the returned JSON, or redirect CLI stdout to a chosen file, then explicitly share or delete that file. Luda creates no report archive and has no automatic retention, upload, deletion or replay mechanism.

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

The safe-code/verb/build-identity follow-up at `7244781` passed 624 unit
tests and 23 private-desktop MCP checks. A real root bootstrap upgrade then
selected `0.1.0-32f10eb9e0f565de` under the test installation prefix, with
system provisioning skipped. Its payload manifest verified; wheel SHA-256 was
`b762256a3b0de901ca2c43cd3b2ace2954fc808e851525e48ec50011ba71190b`.
All 23 MCP checks passed again using that installed wheel and copied independent
fixtures, under UID 1001 on KasmVNC with the shared lease. Installed CLI report
returned ready health, matching build hashes, fresh-process scope and no prior
operations. Evidence is retained under `artifacts/report-identity/installed-7244781/`.
The source qualification fingerprint was
`0569ca1ecc0b1a43b950d172310575cd0065959cdfacd8def08cc98ead28af8f`;
this installed result does not imply Mac host registration.
