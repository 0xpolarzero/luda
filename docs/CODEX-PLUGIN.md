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

## Update

First [upgrade the runtime](INSTALLATION.md#upgrade) from the reviewed new checkout. Build a **new, persistent** marketplace directory from that same checkout. Keep the old directory until the replacement is installed and verified. For example, choose a new path for each upgrade:

```sh
python3 scripts/build_plugin.py --prefix /opt/luda \
  --marketplace-root "$HOME/.local/share/luda-marketplace-next"
```

If your original bundle used `--user`, include that same account option again. The builder refuses existing output; choose another fresh path on subsequent updates. Once the new bundle has been built successfully, replace the old registration:

```sh
codex plugin remove luda@luda-local
codex plugin marketplace remove luda-local
codex plugin marketplace add "$HOME/.local/share/luda-marketplace-next"
codex plugin add luda@luda-local
```

These commands remove the installed plugin cache and old marketplace registration, not the old source directory. If replacement fails, re-add the old marketplace path and reinstall `luda@luda-local`. Restart Codex and run the readiness checks before deleting any obsolete bundle. Do not delete the currently registered marketplace directory.

The runtime's `current` symlink updates the executable selected for new MCP processes; it does not refresh the copied plugin skill. Rebuilding and reinstalling supplies the new skill and references. `codex plugin marketplace upgrade` refreshes Git marketplace snapshots and is not the update mechanism for this generated local bundle.

The removal/replacement sequence and session-launcher arguments were exercised with Codex CLI 0.155.1 in a temporary profile, including a changed skill and preservation of the old source bundle. See [official plugin documentation](https://learn.chatgpt.com/docs/build-plugins) and your installed CLI's `codex plugin --help` for client-version details.
