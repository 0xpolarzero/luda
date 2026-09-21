# Luda

**Let your coding agent use a Linux desktop.**

Luda gives agents tools to see applications, read their controls, click, type, and check what changed. Use it to fill forms, edit documents, work with files, or test a graphical application.

It runs on the Linux machine that owns the desktop. No hosted service or model API is required by Luda.

## How it works

Luda has two parts:

- **Tools** connect your agent to the desktop through MCP, a protocol supported by many coding agents.
- **A skill** teaches the agent how to choose controls, enter text, verify results, and recover when something changes.

The agent can read accessible controls directly or work from screenshots. Actions report whether their result was verified, merely sent, or uncertain. Clicking “Save,” for example, is not itself proof that a file was saved.

## Install: tools and skill together

Run these commands **on the Linux machine whose desktop the agent will control**. You need an existing **Linux X11 desktop**, Python 3.12+, and Git. Ubuntu 24.04 with XFCE is the tested starting point. Wayland and Xwayland are not supported.

```sh
git clone --branch v0.3.1 --depth 1 https://github.com/0xpolarzero/luda.git
cd luda
sudo bash scripts/install.sh --user "$(id -un)"
```

The installer installs the runtime and Linux dependencies, shows detected and supported agents, and lets you select one or several. It then **registers the computer-use tools and installs their skill for your account**. Restart/reconnect your agent and ask: **“Use Luda to inspect my desktop.”** The skill is discoverable by the agent; the client decides when to load it.

Already know your agent? Use `--agent codex --yes`, for example:

```sh
sudo bash scripts/install.sh --user "$(id -un)" --agent codex --yes
```

Use `bash scripts/install.sh --list-agents` for all supported identifiers. Other agents can use a [portable tools-and-skill export](docs/INSTALLATION.md#other-agents-and-custom-profiles). Installation delegates to pinned versions of [Vercel `skills`](https://github.com/vercel-labs/skills) and [`add-mcp`](https://github.com/neon-solutions/add-mcp). It preserves unrelated settings, updates Luda’s own skill and MCP entry, and does not install or authenticate the agent itself. Required installer tooling is supplied automatically; no separate Node installation is needed.

**Codex connected to a VM through its built-in SSH connection?** Run installation **inside the VM**, selecting the Linux account used by that connection. Codex's backend there loads the skill and tool registration. Running an ordinary `ssh` command from a local agent does not automatically load the VM's configuration.

**Building a VM or machine image?** Run the same installer as root with an explicit account and all supported agents:

```sh
bash scripts/install.sh --user YOUR_ACCOUNT --agent all --yes
```

The account must already exist; use `--user root` explicitly when root is the intended agent account. Supported agents do not need to be installed yet, and existing agent settings can already be present. Use repeated `--agent NAME` options to select a subset instead. No running desktop or agent credentials are needed during the build. Start the desktop before using the tools. See the [image recipe and first-boot checks](docs/ENVIRONMENT-PACKAGING.md).

You can also ask your agent:

> Read Luda's README and installation guide. Install the released version on the Linux desktop machine, register its MCP tools and complete skill for my agent account, preserve unrelated configuration, and verify readiness. If this is an image build, configure everything without requiring a running desktop.

[Installation, upgrades and custom agents](docs/INSTALLATION.md) · [Agent connection details](docs/AGENT-INTEGRATIONS.md) · [Release downloads](https://github.com/0xpolarzero/luda/releases)

## What can it do?

- **Work with applications:** find and activate windows, inspect controls, operate menus, select items, and manage windows or workspaces.
- **Enter and check text:** Unicode, multiple lines, selections, clipboard paste, and readback where the application supports it.
- **Use the screen:** screenshots, clicks, drags, scrolling, and keyboard shortcuts. Optional OCR, image matching, and recording provide additional ways to observe.
- **Handle interruptions:** wait for changes, cancel work, pause agent input, and recover owned input after a disconnect.

**Watch the agent work with as little disruption as possible.** Luda shows a distinct agent cursor where supported and tries to leave your mouse, keyboard, and foreground windows undisturbed. The cursor is drawn into the desktop image, so ordinary desktop viewers can display it.

Luda automatically chooses background actions or independent input where supported. When compatibility requires it, Luda uses ordinary foreground mouse/keyboard control, which can move your pointer, redirect keyboard input, and bring windows forward. Application behavior can also change focus. The agent uses the same tools with no mode selection. See [input routing and evidence](docs/BACKGROUND-EXPERIENCE.md).

The optional browser provider opens a temporary Chromium session for ordinary web fields. Existing browser profiles are not attached automatically.

### Optional editor add-on

**[Editor Bridge](addons/editor-bridge/README.md)** adds exact rich-text verification for applications built with ProseMirror. It is a separate installation with its own tools and skill, and the application's developer must also register the adapter. **It is not included or enabled by installing core Luda.** Most desktop tasks do not need it.

## Package it into an environment

You can preinstall Luda in a workstation, container with a graphical session, or VM image. Your integration provisions the desktop and accounts, then runs Luda's installer to configure the chosen agents.

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
