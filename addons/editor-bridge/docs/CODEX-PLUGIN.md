# Install the separate Codex plugin

The simpler alternative is [direct MCP registration plus the skill](../README.md#installed-files-and-removal). Choose one method. This plugin contains only the Editor Bridge; it does not register core Luda.

First install the add-on runtime as described in the README. Then choose a **fresh, persistent** marketplace directory and copy the installed plugin files into a folder named `editor-bridge`:

```sh
mkdir -p ~/.local/share/luda-editor-marketplace/plugins
cp -R ~/.local/share/luda-editor-bridge/venv/share/luda-editor-bridge \
  ~/.local/share/luda-editor-marketplace/plugins/editor-bridge
mkdir -p ~/.local/share/luda-editor-marketplace/.agents/plugins
```

In `plugins/editor-bridge/.mcp.json`, set the absolute executable and browser environment using the [README configuration](../README.md#install-the-agent-add-on). Use its session-launcher command when needed. The shipped command assumes the executable is already on PATH.

Save this as `.agents/plugins/marketplace.json` inside that marketplace directory:

```json
{
  "name": "luda-editor-local",
  "interface": {"displayName": "Luda Editor Bridge"},
  "plugins": [{
    "name": "editor-bridge",
    "source": {"source": "local", "path": "./plugins/editor-bridge"},
    "policy": {"installation": "AVAILABLE", "authentication": "ON_INSTALL"},
    "category": "Productivity"
  }]
}
```

Register it as your agent account:

```sh
codex plugin marketplace add "$HOME/.local/share/luda-editor-marketplace"
codex plugin add editor-bridge@luda-editor-local
```

Restart Codex. Confirm the separate `luda-editor-bridge` skill and `editor_*` tools are available, then run `editor_doctor`. Application registration is still required; the plugin does not make ordinary websites compatible.

For updates, build a new marketplace directory from the matching new runtime, preserving the existing one. Remove `editor-bridge@luda-editor-local`, remove the `luda-editor-local` marketplace registration, then add the new directory and plugin. Restart and verify before deleting the old directory. This follows the [core plugin's tested replacement procedure](../../../docs/CODEX-PLUGIN.md#update), with the separate names above. Removing this plugin does not remove core Luda.
