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

The installer installs Linux dependencies and Luda, then asks which agents to configure. Select one or several comma-separated IDs. Confirm the selected clients. Both MCP tools and the complete skill are installed. Restart/reconnect the selected clients, then ask **“Use Luda to inspect my desktop.”** User scope is the default, so the setup applies across projects for that account.

For unattended installs, specify the account, agent(s) and `--yes`:

```sh
sudo bash scripts/install.sh --user "$(id -un)" --agent codex --yes
sudo bash scripts/install.sh --user "$(id -un)" --agent claude-code --agent cursor --yes
```

From an existing root shell or image builder, replace `"$(id -un)"` with the actual account name. The account and its home must exist. Use `--user root` when root is the intended agent account. Luda writes agent configuration with the selected account’s permissions and ownership. It does not create accounts, install agents, authenticate them, provision a desktop, or configure SSH.

```sh
bash scripts/install.sh --list-agents
bash scripts/install.sh --help
```

The supported selections currently cover Codex, Claude Code, Cursor, Gemini CLI, OpenCode, VS Code's default local Linux profile, and GitHub Copilot CLI. `--agent all` configures all seven supported clients, including clients installed later. `all` and `auto` cannot be combined with another selection. `--agent auto` selects clients detected by their executable or existing configuration; it cannot detect every custom installation. Explicit `--agent` works before the client is installed, which is useful for images. Agent installation status does not change the policy: empty profiles, populated profiles and files left after uninstalling an agent are all valid targets. Client configuration is delegated to pinned versions of [Vercel `skills`](https://github.com/vercel-labs/skills) and [`add-mcp`](https://github.com/neon-solutions/add-mcp), not maintained separately by Luda. This is not a claim that every client/version has been tested end to end.

The installer uses Ubuntu/Debian `apt-get` for system prerequisites and needs Python 3.12+ already available. On other distributions, provision equivalent dependencies, then pass `--skip-system`. To use a writable user prefix without root:

```sh
bash scripts/install.sh --prefix "$HOME/.local/share/luda" --skip-system --agent codex --yes
```

Runtime and build dependencies are hash-locked. A private JavaScript runtime and pinned installer packages are provisioned automatically inside the managed release, including for `--runtime-only`. You do not need to install Node, `skills` or `add-mcp` yourself. Installation creates an immutable versioned release and switches `current` atomically. Keep that installation at the original absolute path. A runtime failure preserves the previous release. Agent setup happens afterward: if it fails, the installed runtime remains available and setup can be retried without rebuilding it. Setup preserves unrelated client settings and other MCP servers and skills. The named `luda` MCP entry and skill are updated, including any local customizations: back those up outside the discovery directory before reinstalling if needed. Malformed MCP configuration is left untouched and reported as a failure. When upgrading from the older installer, unchanged legacy skill copies tracked by Luda are removed after successful registration; edited copies are preserved with a message explaining how to resolve a duplicate. Changes across clients are not one transaction. A failure returns a nonzero status, identifies the failed step and leaves completed steps in place; repeat the same setup command to retry.

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

`--user` selects an OS account, not a client’s named profile. When running as that account, `CODEX_HOME` and `XDG_CONFIG_HOME` for OpenCode and VS Code are supported. An explicitly set `XDG_CONFIG_HOME` is rejected when Copilot is selected because its upstream skill and MCP installers disagree about that profile. `COPILOT_HOME`, `CLAUDE_CONFIG_DIR`, `GEMINI_CLI_HOME`, and OpenCode `OPENCODE_CONFIG`/`OPENCODE_CONFIG_DIR` overrides are rejected for the affected client instead of silently configuring another profile. Root-to-user setup uses the selected account’s standard home locations rather than root’s overrides. For other custom profiles, use the export below.

## Command options

`bash scripts/install.sh` installs the managed runtime and optionally configures agents. `luda setup` configures an already installed managed runtime. Both accept:

| Option | Behavior |
| --- | --- |
| `--user ACCOUNT` | Target existing OS account; defaults to current user, but must be explicit when root. |
| `--agent NAME` | Repeatable explicit client selection; no installed executable required. |
| `--agent all` | Every client supported by this Luda release. |
| `--agent auto` | Detected clients only; unsuitable when preparing for agents installed later. |
| `--list-agents` | List supported identifiers without installation. |
| `--prefix PATH` | Absolute managed runtime location; default `/opt/luda`. |
| `--scope user\|project` | User-wide setup by default, or one project. |
| `--project PATH` | Existing project directory; required with project scope. |
| `--session discover\|direct` | Discover the account’s desktop, or inherit the agent’s GUI environment. |
| `--yes` | Apply without prompting; still requires explicit agent selection or export. |
| `--export PATH` | Export a portable plugin instead of registering clients. |
| `--check-desktop` | Also check the live desktop; omit when building images. |
| `--help` | Print usage. |

Only `install.sh` accepts `--runtime-only` (no client setup), `--skip-system` (prerequisites already provisioned), and `--browser-config FILE` (existing managed Chromium configuration). Runtime-only cannot be combined with agent setup options. Without selection, a terminal offers a client choice; noninteractive installation must supply agents, an export destination, or runtime-only.

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

For an environment that already provides the system prerequisites, download the core `luda-0.3.0-py3-none-any.whl` from [GitHub releases](https://github.com/0xpolarzero/luda/releases). Install it in its own environment:

```sh
python3 -m venv ~/.local/share/luda/venv
~/.local/share/luda/venv/bin/pip install /absolute/download/path/luda-0.3.0-py3-none-any.whl
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

The runtime switches to the new immutable release. Setup updates Luda’s skill and named MCP registration; repeated installation is supported. Unrelated settings, other server entries and other skills are preserved.

An existing same-name `luda` skill or MCP entry is replaced even if it was customized or installed separately. Back up customizations before upgrading. Native plugins have their own update procedure; see [Codex plugin updates](CODEX-PLUGIN.md#update).

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

Installer test coverage and its limits are recorded in [Installer validation](INSTALLER-VALIDATION.md).
