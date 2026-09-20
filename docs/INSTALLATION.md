# Linux installation

Luda attaches to an existing graphical session. It does not install a desktop, start a login session, or require a particular machine manager.

## Prerequisites

- Linux, Python 3.12+, Python venv support.
- Native X11 with XTEST, XInput and RandR; an EWMH window manager. Ubuntu 24.04 with XFCE/XFWM4 and private Xvfb/XFWM4 sessions are tested.
- `xdotool`, `wmctrl`, `scrot`, `xclip`, `x11-utils`, and the X11/XInput/XTest/RandR shared libraries.
- A session D-Bus and AT-SPI2 accessibility bridge for semantic tools; system Python GI with Atspi and Pango introspection.
- Fonts for the scripts you use. The Ubuntu installer includes international and emoji fonts.

Wayland and Xwayland are unsupported. Other native X11 window managers must meet the same contracts but are not universally qualified. Accessibility depends on application providers; screenshots and pointer/keyboard tools remain the fallback where appropriate. OCR, recording and owned-browser tools have separately documented optional dependencies.

## Install everything for your agent

From a released checkout or extracted core source archive, run as your desktop/agent account:

```sh
sudo bash scripts/install.sh --user "$(id -un)"
```

The installer installs Linux dependencies and Luda, then asks which agents to configure. Select one or several comma-separated IDs. Confirm the displayed destinations. Both MCP tools and the complete skill are installed. Restart/reconnect the selected clients, then ask **“Use Luda to inspect my desktop.”** User scope is the default, so the setup applies across projects for that account.

For unattended installs, specify the account, agent(s) and `--yes`:

```sh
sudo bash scripts/install.sh --user "$(id -un)" --agent codex --yes
sudo bash scripts/install.sh --user "$(id -un)" --agent claude-code --agent cursor --yes
```

From an existing root shell or image builder, replace `"$(id -un)"` with the actual account name. The account and its home must exist. Luda writes agent configuration as that account, not as root. It does not create accounts, install agents, authenticate them, provision a desktop, or configure SSH.

```sh
bash scripts/install.sh --list-agents
bash scripts/install.sh --help
```

Automatic adapters currently cover Codex, Claude Code, Cursor, Gemini CLI, OpenCode, VS Code's default local Linux profile, and GitHub Copilot CLI. `--agent auto` selects clients detected by their executable or existing configuration; it cannot detect every custom installation. Explicit `--agent` works before the client is installed, which is useful for images. These are documented configuration adapters, not a claim that every client/version has been tested end to end.

The installer uses Ubuntu/Debian `apt-get` for system prerequisites and needs Python 3.12+ already available. On other distributions, provision equivalent dependencies, then pass `--skip-system`. To use a writable user prefix without root:

```sh
bash scripts/install.sh --prefix "$HOME/.local/share/luda" --skip-system --agent codex --yes
```

Runtime and build dependencies are hash-locked. Installation creates an immutable versioned release and switches `current` atomically. Keep that installation at the original absolute path. A runtime failure preserves the previous release. Agent setup happens afterward: if it fails, the installed runtime remains available and setup can be retried without rebuilding it. Setup validates all selected configurations before writing them and rolls back its own file changes on ordinary write errors; it is not a crash-atomic transaction across client files.

By default, tools launch through `luda-session`, which discovers the selected account's XFCE desktop even when the agent starts through SSH. No display number or session secret is baked into configuration. For an agent already running in a non-XFCE graphical session, use `--session direct` to inherit its environment; see [session attachment](#ssh-and-explicit-session-attachment).

## Configure an already installed runtime

Run as the agent account (or as root with `--user ACCOUNT`):

```sh
/opt/luda/current/.venv/bin/luda setup --agent codex --yes
```

For a custom prefix, also pass `--prefix /absolute/prefix`. For one project only:

```sh
/opt/luda/current/.venv/bin/luda setup --agent codex \
  --scope project --project /absolute/project --yes
```

The project must exist and be writable by that account. Client project-trust rules still apply. For VS Code remote projects, use project scope or configure the remote profile explicitly; the user adapter targets the default local Linux profile.

`CODEX_HOME`, `COPILOT_HOME`, and applicable `XDG_CONFIG_HOME` overrides are respected when setup runs as the account. Root-to-user setup uses that account's standard home locations, not root's environment overrides. Other custom profiles should use the export below.

## Other agents and custom profiles

Export the complete skill and MCP launch configuration instead of selecting a built-in adapter:

```sh
/opt/luda/current/.venv/bin/luda setup --export "$HOME/luda-plugin" --yes
```

Choose a new directory. It contains `plugin.json`, `mcp.json`, and `skills/luda/` following the [Agent Plugins format](https://agent-plugins.org/specification). Import it using a compatible client's plugin mechanism, or use `mcp.json` and the skill directory in a custom agent. Exporting does not register or activate the plugin. The configured executable is on this Linux machine: another host needs an explicit transport such as SSH, not that local path alone. Native client plugins and direct setup are alternatives; avoid registering both.

## Verify after starting the desktop

Installation and configuration do not prove that the live desktop or the client is ready. Image builds intentionally skip live checks. For an existing desktop, add `--check-desktop` to install/setup, or run:

```sh
/opt/luda/current/.venv/bin/luda-session --user "$(id -un)" -- \
  /opt/luda/current/.venv/bin/luda doctor
```

A failed live check returns a nonzero exit status but leaves the installed runtime and configuration available. Start/fix the session, then rerun the check. Finally restart the agent, check that the skill is discoverable and tools are connected, and ask it to run `desktop_doctor`, `desktop_windows`, and `desktop_observe`. See [Confirm it works](AGENT-INTEGRATIONS.md#confirm-it-works).

## Runtime only

```sh
sudo bash scripts/install.sh --user "$(id -un)" --runtime-only --yes
```

Use this when the eventual agent account is not yet chosen. It installs the runtime without registering clients. The legacy positional form `scripts/install.sh /opt/luda --user ACCOUNT` remains runtime-only for compatibility.

## Install a downloaded wheel

For an environment that already provides the system prerequisites, download the core `luda-0.2.0-py3-none-any.whl` from [GitHub releases](https://github.com/0xpolarzero/luda/releases). Install it in its own environment:

```sh
python3 -m venv ~/.local/share/luda/venv
~/.local/share/luda/venv/bin/pip install /absolute/download/path/luda-0.2.0-py3-none-any.whl
~/.local/share/luda/venv/bin/luda doctor
```

This installs the core runtime and Python dependencies, without the optional browser or Editor Bridge. It does not install system packages or create the managed `current` layout. In the agent registration examples, use `~/.local/share/luda/venv/bin/luda` expanded to an absolute path. The complete skill is under `~/.local/share/luda/venv/share/luda/skills/luda`; copy that folder to your client's [skill directory](AGENT-INTEGRATIONS.md#choose-your-agent). The session launcher is beside `luda` in `bin`.

Use the matching `SHA256SUMS` release asset to check downloads. A plugin ZIP contains configuration and skill files only; it does not install this runtime. For repeatable image builds and managed rollback, use the source installer above with its locked dependencies.

## SSH and explicit session attachment

When the agent does not inherit the graphical environment, run as the desktop account or root:

```sh
/opt/luda/current/.venv/bin/luda-session --user desktop -- \
  /opt/luda/current/.venv/bin/luda
```

Replace `desktop` with your actual account. Automatic attachment discovers exactly one ready XFCE session for that account. For another session manager, select a process from that account that carries the graphical session environment with `--session-pid PID`. Missing or ambiguous sessions fail; display numbers are not guessed. Required environment includes `DISPLAY`, `DBUS_SESSION_BUS_ADDRESS`, and a readable Xauthority file. Direct invocation can use an already established graphical environment without this discovery helper.

The launcher drops root privileges, uses an allowlisted environment, and changes to the selected account's home (or `/`). `--cwd /absolute/path` selects an accessible working directory. Session readiness waits at most five seconds by default (`--wait 0` through `--wait 30`). It never starts or unlocks a session.

SSH transport must execute the server on the Linux machine that owns the desktop. Keep host keys verified and use stdio; no public MCP listener is needed. A configuration file alone does not create a transport.

## Upgrade

Download/check out the new reviewed release, then rerun the same installer command with the same prefix, account, selected agents, session mode and optional browser configuration:

```sh
sudo bash scripts/install.sh --user "$(id -un)" --agent codex --yes
```

The runtime switches to the new immutable release. Setup refreshes skills previously managed by this installer only when their files remain unmodified. Identical repeated runs are a no-op for agent files. Unrelated settings and other skills are preserved.

If a `luda` tool registration already differs, or a skill was edited or installed separately with different contents, setup stops before changing selected clients. Back up the existing skill outside its discovery directory, review/remove only the conflicting Luda MCP entry, and rerun `luda setup`. Do not remove other servers or client settings. Native plugins have their own update procedure; see [Codex plugin updates](CODEX-PLUGIN.md#update).

Restart/reconnect clients after updating: running MCP processes still use their previous code. Repeat the read-only readiness checks. A runtime-only upgrade does not refresh account skills; run setup for each configured account.

## Rollback and removal

```sh
sudo python3 scripts/manage_install.py rollback --prefix /opt/luda \
  --user desktop --release VERSION-SOURCEHASH
sudo python3 scripts/manage_install.py uninstall --prefix /opt/luda
```

Release IDs are recorded in `/opt/luda/.luda-install.json`. Reconnect clients after selecting a different release. Uninstall preserves modified and unknown files and external agent settings. Stop clients before uninstalling; remove their Luda registration separately while preserving other entries.

`desktop_doctor` reports actual dependency and capability availability. Missing `wmctrl` prevents target enumeration; missing `xdotool` prevents focus-dependent input while read-only screenshot/accessibility capabilities can remain available. Installed files alone are not evidence of a ready desktop.

## Package into an environment

For an image, VM or managed Linux workstation, see [environment packaging](ENVIRONMENT-PACKAGING.md). Install the runtime once and register each selected agent for its own account; user-wide discovery then works across project folders. Desktop provisioning and account lifecycle belong to the integrator.
