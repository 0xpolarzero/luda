# Setup and discovery

Use this guide when Luda tools are missing or cannot reach the intended desktop. If connected tools already work, start with `desktop_doctor` instead of reinstalling.

## Three separate pieces

1. **Linux runtime:** Luda's MCP server and graphical system prerequisites live on the machine with the desktop.
2. **Agent connection:** the coding agent launches/connects to that server over MCP stdio, locally or through an explicit SSH command.
3. **Skill:** this whole folder teaches the agent how to use those tools. Copying `SKILL.md` alone loses the task references; copying the folder does not register a server.

An installer, VM image builder, or administrator decides where to provision these pieces and which accounts receive them. Luda does not create a graphical session, install an agent into every project, or assume a sandbox manager. User-scope skill/MCP registration is normally appropriate when the same agent account should use Luda from any working folder. Project scope applies only to that project. Different agents/accounts still need their own supported discovery and connection settings.

## Supported environment

The actual graphical backend is native Linux X11 with XTEST, XInput, RandR, and an EWMH window manager. Ubuntu 24.04 with XFCE/XFWM4 and private Xvfb/XFWM4 sessions are tested. Wayland and Xwayland are unsupported. Other X11 managers must meet the contracts but are not universally qualified.

Runtime requires Python 3.12+ and the declared package dependencies. Desktop tools require `wmctrl`, `xdotool`, `scrot`, `xclip`, X11 utilities/shared libraries, and access to the selected display. Semantic tools additionally need session D-Bus, AT-SPI2, and system Python GI/Atspi/Pango support. The supported application's accessibility provider must expose the relevant interfaces. Install appropriate fonts for the text scripts in use. Optional browser/OCR/media dependencies are separate.

Doctor distinguishes available capabilities. Missing `wmctrl` prevents target enumeration; missing `xdotool` prevents focus-dependent input while some read-only capabilities can remain usable. Installed packages alone do not establish display access or a ready session.

## Install from a trusted checkout

Read the checkout's `docs/INSTALLATION.md` and `docs/AGENT-INTEGRATIONS.md` for the current commands and client-native configuration. Official source: https://github.com/0xpolarzero/luda. Use a trusted selected checkout/release rather than silently executing code from an unrelated similarly named package.

The managed Linux installer installs runtime, MCP registration and the complete skill together:

```sh
sudo bash scripts/install.sh --user "$(id -un)" --agent codex --yes
```

Run from the checkout as the intended agent account, so `id -un` expands before sudo. When already root, name the target account explicitly; `--user root` is supported. Repeat `--agent NAME` for a subset, or use `--agent all` for every supported client, even before clients are installed. Use `--list-agents` to see identifiers. The Debian/Ubuntu installer provisions system packages but requires Python 3.12+ already available; on other distributions provision equivalent prerequisites and use `--skip-system`.

The installer supplies pinned Vercel `skills`, `add-mcp` and their private runtime automatically. It copies the complete skill and merges MCP configuration through those upstream tools. Unrelated settings, servers and skills are preserved. Existing same-name Luda entries are updated, including customizations: preserve any desired customizations before reinstalling. Installation or configuration changes must stay within the user’s requested scope.

After installation, the selected release’s server is `/opt/luda/current/.venv/bin/luda`. To configure more clients without reinstalling the runtime:

```sh
/opt/luda/current/.venv/bin/luda setup --agent all --yes
```

User scope is default. For one project add `--scope project --project /absolute/project`. Root must specify `--user ACCOUNT`. The target account must exist; no installed agent executable, login or running desktop is required to configure it. Default profile locations belong to the selected OS user. Read `docs/INSTALLATION.md` before using custom client-profile environment overrides; unsupported overrides are rejected.

For an image that will create the agent account later, install with `--runtime-only`, then run `luda setup --user ACCOUNT --agent all --yes` after account creation. Runtime-only does not register tools or skills. Setup failures may leave successful registrations in place; read the reported failed phase and rerun the same command after fixing it.

Reload/reconnect the client as its documentation requires, confirm Luda tools are exposed, then call `desktop_doctor`. Client trust or MCP approval can still be necessary. Installing configuration does not prove the client loaded it or that the desktop is ready. Use `luda setup --export /absolute/new/plugin --yes` for a portable skill/MCP bundle rather than guessing another client’s configuration. Export does not activate the plugin.

## SSH and session attachment

The server must execute on the Linux machine owning the display, as that desktop account. When a shell/SSH session does not inherit the graphical environment, use the explicit launcher:

```sh
/opt/luda/current/.venv/bin/luda-session --user desktop -- \
  /opt/luda/current/.venv/bin/luda
```

Replace `desktop` with the actual account. The launcher can run as that account or root; it drops root privileges and uses a selected environment. Automatic discovery requires exactly one ready XFCE session. To choose a specific session or another session manager, provide `--session-pid PID` for a process of that account carrying the intended graphical environment. DISPLAY, session D-Bus, and a readable Xauthority file are required; do not invent their values. The helper does not start or unlock a session.

By default it waits up to five seconds (configurable `--wait 0` through `--wait 30`) and changes to the desktop account's home or `/`; `--cwd /absolute/path` selects another accessible directory. Ambient browser configuration is not simply inherited through its sanitized environment; use the managed installation's documented optional-browser configuration.

For remote use, the agent's MCP command must establish the SSH stdio transport and execute the launcher/server remotely. A configuration file on the wrong machine does not create that transport. Keep normal host-key verification; a public HTTP/MCP listener is unnecessary.

## Check the installation boundary

The loaded skill and server can have different versions if an integration copies one without updating the other. Doctor reports the server's tool identity and bundled `SKILL.md` identity; that skill hash does not cover the reference folder or prove which skill the client loaded. If examples disagree with registered schemas, inspect the actual schema and align the installation rather than inventing arguments.

A packaged VM can provision runtime once and install/register tools and skills for its intended agent accounts. See `docs/ENVIRONMENT-PACKAGING.md` in the checkout for that operator responsibility. No project-specific bootstrapping should be needed after a correct user-scope integration, but each client still has to load its own supported configuration.
