# Luda

**Let your coding agent use a Linux desktop.**

Luda gives agents tools to see applications, read their controls, click, type, and check what changed. Use it to fill forms, edit documents, work with files, or test a graphical application.

It runs on the Linux machine that owns the desktop. No hosted service or model API is required by Luda.

## How it works

Luda has two parts:

- **Tools** connect your agent to the desktop through MCP, a protocol supported by many coding agents.
- **A skill** teaches the agent how to choose controls, enter text, verify results, and recover when something changes.

The agent can read accessible controls directly or work from screenshots. Actions report whether their result was verified, merely sent, or uncertain. Clicking “Save,” for example, is not itself proof that a file was saved.

## Get started

You need an existing **Linux X11 desktop** and **Python 3.12 or newer**. Ubuntu 24.04 with XFCE is the tested starting point. Wayland and Xwayland are not supported.

On that Linux machine, from your desktop account:

```sh
git clone https://github.com/0xpolarzero/luda.git
cd luda
sudo bash scripts/install.sh /opt/luda --user "$(id -un)"
/opt/luda/current/.venv/bin/luda doctor
```

Run the diagnostic from your graphical session. If you connect over SSH, follow [session attachment](docs/INSTALLATION.md#ssh-and-explicit-session-attachment).

**Next: [connect your agent](docs/AGENT-INTEGRATIONS.md).** The guide covers Codex, Claude Code, Cursor, Gemini CLI, and OpenCode, with account-wide and project installation options. Installing the runtime alone does not register the tools or skill with your agent.

You can also ask an agent with terminal access:

> Read Luda's installation and agent-integration guides. Install it for this Linux desktop and make its tools and skill available to your agent account. Preserve unrelated configuration.

For other Linux distributions, existing dependencies, updates, and removal, see [installation](docs/INSTALLATION.md). Downloadable packages are listed under [releases](https://github.com/0xpolarzero/luda/releases).

## What can it do?

- **Work with applications:** find and activate windows, inspect controls, operate menus, select items, and manage windows or workspaces.
- **Enter and check text:** Unicode, multiple lines, selections, clipboard paste, and readback where the application supports it.
- **Use the screen:** screenshots, clicks, drags, scrolling, and keyboard shortcuts. Optional OCR, image matching, and recording provide additional ways to observe.
- **Handle interruptions:** wait for changes, cancel work, pause agent input, and recover owned input after a disconnect.

Luda automatically chooses background actions or independent input where supported, and uses ordinary foreground mouse/keyboard control when needed for compatibility. The agent uses the same tools with no mode selection. A distinct agent cursor appears in desktop pixels when available, so ordinary desktop viewers can display it. Foreground fallback can move your pointer and change focus; application callbacks can also bring windows forward. See [input routing and evidence](docs/BACKGROUND-EXPERIENCE.md).

The optional browser provider opens a temporary Chromium session for ordinary web fields. Existing browser profiles are not attached automatically.

### Optional editor add-on

**[Editor Bridge](addons/editor-bridge/README.md)** adds exact rich-text verification for applications built with ProseMirror. It is a separate installation with its own tools and skill, and the application's developer must also register the adapter. **It is not included or enabled by installing core Luda.** Most desktop tasks do not need it.

## Package it into an environment

You can preinstall Luda in a workstation, container with a graphical session, or VM image. Your integration owns desktop provisioning, account setup, and agent registration. Luda supplies the runtime, skill files, and explicit setup commands.

Use the [environment packaging guide](docs/ENVIRONMENT-PACKAGING.md) to make tools and skills available across folders for each agent account. There is no universal installation directory that every agent automatically discovers.

## Learn more

| I want to… | Read |
| --- | --- |
| Install or attach to a graphical session | [Installation](docs/INSTALLATION.md) |
| Connect an agent and install its skill | [Agent integrations](docs/AGENT-INTEGRATIONS.md) |
| Understand the tools and their parameters | [Tool reference](docs/TOOLS.md) |
| Read the agent's operating instructions | [Core skill](skills/luda/SKILL.md) |
| Check supported backends and known limits | [Backend support](docs/BACKEND-SUPPORT.md) · [Validation](docs/VALIDATION.md) |
| Build packages or contribute | [Development and releases](docs/DEVELOPMENT.md) |

Application accessibility varies, and human input can race with an agent. Luda reports these limits rather than treating every dispatched action as success.

[MIT license](LICENSE).
