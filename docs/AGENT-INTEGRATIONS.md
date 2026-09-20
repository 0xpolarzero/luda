# Connect your agent

Luda has two parts: **MCP tools** operate the desktop; the **skill** teaches the agent how to use them. Install both for the agent account. User scope makes them available across that account's projects. It does not configure other accounts or computers.

First [install the Linux runtime](INSTALLATION.md). The examples below assume `/opt/luda` and an agent running inside the graphical session. If it runs over SSH or without the desktop environment, use the [session launcher](#agents-without-a-graphical-environment).

## Choose your agent

Run the skill command from this repository as the agent account, without sudo:

```sh
python3 scripts/install_skill.py --agent codex --scope user
```

Replace `codex` with `claude`, `cursor`, `gemini`, or `opencode`. This copies the complete skill, including its reference files. It never edits MCP configuration. An identical installation is a no-op; different existing content is preserved and installation stops. To update, move the old `luda` skill directory to a backup outside the discovery directory, then rerun. To remove, delete only that skill directory and separately remove the agent's Luda MCP entry.

| Agent | User skill directory | Register the tools |
| --- | --- | --- |
| Codex | `~/.agents/skills/luda` | CLI command below, or [Codex plugin](CODEX-PLUGIN.md) |
| Claude Code | `~/.claude/skills/luda` | CLI command below |
| Cursor | `~/.cursor/skills/luda` | Add the JSON entry below to `~/.cursor/mcp.json` |
| Gemini CLI | `~/.gemini/skills/luda` | CLI command below |
| OpenCode | `~/.config/opencode/skills/luda` | Add the JSON entry below to `~/.config/opencode/opencode.json` |

OpenCode respects `XDG_CONFIG_HOME` when set. Other clients can override their profile locations; the table uses their standard profiles. For a single project, use `--scope project --project /absolute/project`; OpenCode uses `.opencode/skills`, and the others use their corresponding project directory. Configure MCP in the client's project scope separately.

### Codex, Claude Code, Gemini CLI

Choose **one** command for your client. Check its existing MCP list first: if `luda` exists, review that registration rather than replacing it blindly.

```sh
codex mcp add luda -- /opt/luda/current/.venv/bin/luda
claude mcp add --transport stdio --scope user luda -- /opt/luda/current/.venv/bin/luda
gemini mcp add --transport stdio --scope user luda /opt/luda/current/.venv/bin/luda
```

For Codex, choose either direct MCP plus skill installation or the plugin, not both. The plugin already supplies the skill and tool registration.

### Cursor

Merge just the `luda` member into the existing `mcpServers` object in `~/.cursor/mcp.json`. Preserve other settings and servers; do not replace the entire file.

```json
{
  "mcpServers": {
    "luda": {
      "command": "/opt/luda/current/.venv/bin/luda",
      "args": []
    }
  }
}
```

### OpenCode

Merge just the `luda` member into the existing `mcp` object in `~/.config/opencode/opencode.json` (or your existing `.jsonc` configuration).

```json
{
  "mcp": {
    "luda": {
      "type": "local",
      "command": ["/opt/luda/current/.venv/bin/luda"],
      "enabled": true
    }
  }
}
```

## Agents without a graphical environment

A same-machine agent running over SSH often lacks the desktop's environment. Replace the executable with the session launcher and its arguments:

```sh
/opt/luda/current/.venv/bin/luda-session --user YOUR_DESKTOP_ACCOUNT -- /opt/luda/current/.venv/bin/luda
```

Use that executable and argument list in your client's registration. It attaches to an existing session; it does not start one. Run as the desktop account, or use an explicitly authorized root launcher that drops to that account. Other ordinary accounts cannot attach by naming someone else's account. XFCE discovery and explicit `--session-pid` attachment are explained in [installation](INSTALLATION.md).

If the agent itself runs on another computer, its MCP command must establish SSH and launch Luda **on the Linux desktop machine**. Local `/opt/luda` paths do not magically refer to a remote machine. Use your existing SSH configuration, verified host keys, and stdio (`ssh -T`); the skill must be installed where that agent discovers skills. Cursor's local user skills are not automatically copied into remote or cloud workers. See [VM images](ENVIRONMENT-PACKAGING.md) for guest-side setup.

## Confirm it works

Restart the client, confirm the `luda` skill is listed, and ask it:

> Use Luda to check desktop readiness, list windows, and show a screenshot of one window. Do not change anything.

The expected calls are `desktop_doctor`, `desktop_windows`, and `desktop_observe`. If tools are missing, fix MCP registration. If the skill is missing, fix its discovery location. If doctor reports no graphical session or a missing dependency, fix the Linux environment. Client approval/trust policies still apply; installing a skill does not override them.

## Compatibility and sources

Luda uses local MCP stdio and ordinary `SKILL.md` folders. Codex plugin registration and MCP workflows are exercised in this repository's tests. The other recipes follow the official client documentation; they are compatibility instructions, **not claims of an end-to-end qualification run for every client/version**. Other MCP clients can use the same server if they support image results and local stdio, with instructions installed by their own mechanism.

Documentation checked September 2026: [Codex MCP](https://learn.chatgpt.com/docs/extend/mcp?surface=cli), [Codex skills](https://learn.chatgpt.com/docs/build-skills), [Claude Code MCP](https://code.claude.com/docs/en/mcp), [Claude skills](https://code.claude.com/docs/en/skills), [Cursor MCP](https://docs.cursor.com/context/model-context-protocol), [Cursor skills](https://prod.cursor.com/docs/skills), [Gemini MCP](https://geminicli.com/docs/tools/mcp-server/), [Gemini skills](https://geminicli.com/docs/cli/skills/), [OpenCode MCP](https://opencode.ai/docs/mcp-servers/), [OpenCode skills](https://opencode.ai/docs/skills/).
