# Protocol and upgrade compatibility

MCP initialization advertises the installed **Luda package version**, not the MCP SDK version. MCP protocol negotiation itself remains the pinned SDK's responsibility. Tool schemas returned by `tools/list` are authoritative for the running server, including argument types, enums and refusal of unknown parameters. Read `desktop_doctor` after reconnect or installation changes.

Version 0.1 is experimental. No cross-minor tool compatibility is promised before a stable 1.0 contract. A future breaking change must update the package version, describe renamed/removed tools and result changes, and update the bundled skill and plugin together. Within a release, new optional result fields must not change the meaning of existing `effect`, error codes or verified conditions. Consumers should ignore unknown response fields and must handle unknown error codes as failures requiring inspection, not as successful input.

Upgrading files does not replace an already-running MCP process. Close/reopen the agent connection to load the selected release; then discard cached tool schemas, window IDs, elements and screenshot IDs. `desktop_reconnect` changes the attached desktop session inside the existing process; it does not upgrade that process. No saved mutation is replayed on either transition.

The versioned installer validates recorded payloads before reusing or rolling back a release and preserves the current selection on failed preparation. Rollback chooses a prior executable/skill release, not an old desktop state. Documents, running applications and external agent configuration are not rolled back. Regenerate/reinstall a plugin when its prefix, account, placement or bundled skill changes.

The stdio transport is the supported runtime interface. Generated configurations and plugin manifests were locally checked with Codex CLI 0.155.1. Remote-executor placement remains experimental and requires the actual Mac SSH client test; it is not established by protocol negotiation or package version equality.
