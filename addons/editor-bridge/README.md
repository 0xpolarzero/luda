# Luda Editor Bridge

**Verify rich-text edits in applications you control.** A separate, optional add-on for [Luda](../../README.md).

Luda operates Linux applications. This add-on connects to a specially prepared **ProseMirror** editor so an agent can read its document text, paragraphs, bold/italic marks and selection, then check an edit precisely. For example, replace a sentence and verify that the surrounding bold text remained intact.

**It is not included or activated by installing Luda. It does not adapt arbitrary websites.** You need both the agent add-on and a small adapter installed by the application's developer. Verification checks document contents, not saving.

## Install the agent add-on

Requires the same supported Linux/X11 session as Luda, Python 3.12+, a compatible Chromium executable, and permission to run Chromium's sandbox. The add-on installs Playwright; it never downloads Chromium automatically. `xclip` is additionally required for explicit clipboard range editing.

From a checkout of the same Luda release, install into a **separate environment**:

```sh
python3 -m venv ~/.local/share/luda-editor-bridge/venv
~/.local/share/luda-editor-bridge/venv/bin/pip install '.[browser]' ./addons/editor-bridge
```

Run those commands from the repository root. Both source packages are supplied explicitly: no published `luda` package on PyPI is assumed. For release wheels, install the matching `luda` and `luda_editor_bridge` wheel files together in that environment instead.

Add a separate stdio MCP server to your agent's configuration, replacing the example account and browser paths:

```json
{
  "mcpServers": {
    "luda-editor-bridge": {
      "command": "/home/you/.local/share/luda-editor-bridge/venv/bin/luda-editor-bridge",
      "env": {"LUDA_CHROMIUM_EXECUTABLE": "/absolute/path/to/chrome"}
    }
  }
}
```

The process needs the graphical account's real `DISPLAY`, `XAUTHORITY` when used, and session D-Bus environment, just like core Luda. For an agent over SSH, attach first and set the browser variable **after** `luda-session` (it intentionally sanitizes inherited variables):

```sh
~/.local/share/luda-editor-bridge/venv/bin/luda-session --user "$(id -un)" -- /usr/bin/env LUDA_CHROMIUM_EXECUTABLE=/absolute/path/to/chrome "$HOME/.local/share/luda-editor-bridge/venv/bin/luda-editor-bridge"
```

Use this executable/argument sequence in the MCP registration. The agent must run on that Linux machine as the graphical account, or an explicitly authorized root launcher must select it. Do not run a root browser or disable Chromium's sandbox to bypass missing prerequisites.

Install **only this add-on's skill** into the agent's additional skill location, for example:

```sh
mkdir -p ~/.agents/skills
cp -R addons/editor-bridge/skills/luda-editor-bridge ~/.agents/skills/
```

For Codex's plugin format, this directory also contains a separate plugin manifest and `.mcp.json`. Its default MCP command requires `luda-editor-bridge` on the agent host's `PATH`; otherwise configure the absolute executable above. See the repository's [agent integration guide](../../docs/AGENT-INTEGRATIONS.md) for client-specific installation and environment wiring. Core Luda registration does not register this add-on.

### Installed files and removal

Wheel/source installation also places the complete skill and application adapter under:

```text
~/.local/share/luda-editor-bridge/venv/share/luda-editor-bridge/
  .codex-plugin/plugin.json
  .mcp.json
  skills/luda-editor-bridge/
  application/luda-prosemirror.mjs
```

For wheel-only installs, copy the skill from that `skills` directory and give the application developer the module from `application`. [GitHub releases](https://github.com/0xpolarzero/luda/releases) publish matching assets when available; install both downloaded wheel paths with the add-on environment's `pip install /path/to/luda-…whl /path/to/luda_editor_bridge-…whl`. Do not install an unrelated similarly named package.

For Codex, direct MCP registration plus the separate skill above is a complete supported setup:

```sh
codex mcp add luda-editor-bridge -- /usr/bin/env LUDA_CHROMIUM_EXECUTABLE=/absolute/path/to/chrome "$HOME/.local/share/luda-editor-bridge/venv/bin/luda-editor-bridge"
```

Alternatively, follow [the separate Codex plugin installation](docs/CODEX-PLUGIN.md). It packages this add-on's registration and skill together. Choose plugin registration or direct MCP plus skill, not both. MCP-only clients use the explicit configuration already shown and install the skill through their own skill mechanism. No setup step modifies another agent's configuration automatically.

To remove the add-on, remove its MCP/plugin registration and `luda-editor-bridge` skill from your agent, then delete only its dedicated environment. Your independently installed core Luda environment and registration remain intact.

## Connect your application

Your application's developer copies `application/luda-prosemirror.mjs` into the application and registers its existing editor view:

```js
import { registerProseMirror } from './luda-prosemirror.mjs';
const unregister = registerProseMirror(view, { paragraphs: 'enter' });
// Call unregister() when destroying or replacing the view.
```

This declares that the app's Enter binding creates paragraphs. The bridge reads and maps editor state; it does not insert text or install key bindings. Optional hard-break support and integration details are in [the application guide](application/README.md).

## Use it

1. Run `~/.local/share/luda-editor-bridge/venv/bin/luda-editor-bridge doctor` in the graphical session to check prerequisites.
2. Ask the agent to use **Luda Editor Bridge** and open your application with `editor_open(url, lifetime="temporary_session")`.
3. `editor_inspect` reports registered editors under `text_fields`, supported capabilities, and connection status. No matching editor? Remove filters, then check that the application registered its view.
4. Read, focus, select, edit and read back. Use `editor_type(..., line_breaks="paragraph")` when text contains newlines. Save through the application's own controls and verify saving separately.

The add-on owns a fresh browser profile. **Closing the server, disconnecting the agent, or calling `editor_close` deletes that browser/profile and loses unsaved content.** It does not attach your usual browser or core Luda's separate browser.

## Supported scope

Basic paragraphs, text, bold/italic marks, and explicitly declared hard breaks. No lists, tables, images, links, custom attributes, frames, shadow-root editors, arbitrary rich editors, or existing-browser attachment. Unsupported document structures are refused rather than silently flattened.

Native typing supports whole-document replacement and append-at-end. Explicit `transport="clipboard"` supports editing selected interior ranges; it leaves the last nonempty inserted segment in CLIPBOARD. No automatic clipboard fallback, save, retry or replay.

See the [agent skill](skills/luda-editor-bridge/SKILL.md) for workflows, limits and failure handling. Installing, updating or removing this add-on does not install, activate or remove core Luda's independently configured server.

## Test the add-on

After installing the source pair into the repository `.venv` for development:

```sh
.venv/bin/python -m unittest discover -s addons/editor-bridge/tests -p 'test_*.py'
.venv/bin/python addons/editor-bridge/scripts/qualify.py --suites owned-rich owned-rich-clipboard owned-hard-breaks rich-progress --executable /absolute/path/to/chrome
```

GUI suites require an ordinary graphical account and the private Xvfb/D-Bus prerequisites documented by the core test harness. They invoke the separate add-on MCP executable and use independent application model/DOM oracles.
