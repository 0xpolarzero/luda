# Codex plugin

Luda's plugin packages an MCP server registration and the complete `skills/luda` folder. Runtime installation is separate. For other clients or standalone MCP registration, see [Connect your agent](AGENT-INTEGRATIONS.md). Choose this plugin or standalone registration, not both. The repository plugin runs `luda` from PATH in the agent's graphical environment.

Build a bundle with an explicit installed path:

```sh
python3 scripts/build_plugin.py --prefix /opt/luda \
  --marketplace-root "$HOME/.local/share/luda-marketplace"
codex plugin marketplace add "$HOME/.local/share/luda-marketplace"
codex plugin add luda@luda-local
```

Use a fresh persistent directory; the builder refuses to overwrite existing output. Run registration as the agent account. The bundled executable runs directly in the agent environment. Add `--user desktop` to the builder only when attachment through `luda-session` is needed; replace `desktop` with the account that owns the graphical session. See [installation](INSTALLATION.md) for discovery limitations.

Restart/reconnect the client, verify that the Luda skill is discoverable, and run `desktop_doctor`, `desktop_windows`, and `desktop_observe`. Plugin installation alone does not establish graphical access.

Other MCP clients can register `/opt/luda/current/.venv/bin/luda` as a stdio server and load the same skill using their own discovery mechanism. No client-specific API credentials are required by Luda. Configure transport separately if the agent runs on another machine.

The builder also supports `--output /absolute/new/luda` for a standalone plugin folder. Optional `--remote` emits an experimental remote-executor placement hint; it neither establishes SSH nor makes local paths available on another machine. Local direct execution is the documented default.
