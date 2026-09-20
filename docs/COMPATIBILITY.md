# Protocol and upgrade compatibility

MCP initialization advertises the installed **Luda package version**, not the MCP SDK version. MCP protocol negotiation itself remains the pinned SDK's responsibility. Tool schemas returned by `tools/list` are authoritative for the running server, including argument types, enums and refusal of unknown parameters. Read `desktop_doctor` after reconnect or installation changes.

Version 0.1 is experimental. No cross-minor tool compatibility is promised before a stable 1.0 contract. A future breaking change must update the package version, describe renamed/removed tools and result changes, and update the bundled skill and plugin together. Within a release, new optional result fields must not change the meaning of existing `effect`, error codes or verified conditions. Consumers should ignore unknown response fields and must handle unknown error codes as failures requiring inspection, not as successful input.

Upgrading files does not replace an already-running MCP process. Close/reopen the agent connection to load the selected release; then discard cached tool schemas, window IDs, elements and screenshot IDs. `desktop_reconnect` changes the attached desktop session inside the existing process; it does not upgrade that process. No saved mutation is replayed on either transition.

The versioned installer validates recorded payloads before reusing or rolling back a release and preserves the current selection on failed preparation. Rollback chooses a prior executable/skill release, not an old desktop state. Documents, running applications and external agent configuration are not rolled back. Regenerate/reinstall a plugin when its prefix, account, placement or bundled skill changes.

The stdio transport is the supported runtime interface. Generated configurations and plugin manifests were locally checked with Codex CLI 0.155.1. Remote-executor placement remains experimental and requires the actual Mac SSH client test; it is not established by protocol negotiation or package version equality.

## Identifying a running contract

`desktop_doctor.versions` (also returned by `luda doctor`) adds identity format 1 without changing the existing
`version`, health or capability fields:

- `driver_version` is the installed Luda distribution version, also advertised
  during MCP initialization. If distribution metadata becomes unreadable after
  startup, this additive field is null rather than failing an otherwise ready doctor.
- `tool_schema.sha256` fingerprints the actual complete `tools/list` declarations.
  Algorithm `sha256-canonical-tools-list-v1` sorts tools by name, serializes their
  JSON-mode declarations with absent optional fields omitted, sorts object keys,
  uses compact separators and UTF-8 without ASCII escaping, then computes SHA-256.
  Descriptions and annotations participate; a changed hash is a changed declared
  artifact, not by itself proof of a breaking API change.
- `bundled_skill.sha256` fingerprints exact bundled `SKILL.md` bytes from the
  installed distribution, or its source artifact for an editable install. Missing,
  unreadable or oversized artifacts report `status=unavailable` with no invented
  version or host path. The read limit is 256 KiB. This does **not** establish which
  skill an external agent loaded; compare the hash with that copied artifact.

These hashes identify content rather than promise compatibility or authenticate
an installation. They do not identify modified driver source beyond its declared
package version. The installer release identity and payload integrity manifest
remain the stronger local release record. Schema caches still need refreshing on
upgrade, and a doctor result never authorizes replay of an old mutation.

The existing migration policy above addresses MCP-10; no previous published
schema migration or cross-version interoperability is qualified here. Focused
public-tool tests cover SHIP-08's additive identity reporting, schema-order
stability, changed schema/skill bytes and unavailable skill artifacts. They do not
prove a remote client's skill discovery or an upgrade between released versions.

CLI and MCP doctor use the same discovery/identity path. A focused CLI regression
checks matching identities and preserves readiness/exit status. Distribution-record
fixtures exercise installed skill lookup and malformed metadata. A separately
built wheel was installed offline into a disposable virtual environment and its
reported skill SHA-256 matched the actual installed `share/luda/skills/luda/SKILL.md`
bytes; this verifies the wheel layout rather than only editable-source discovery.
