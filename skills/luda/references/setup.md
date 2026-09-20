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

The managed Linux installer uses a chosen prefix and desktop account, for example:

```sh
sudo bash scripts/install.sh /opt/luda --user "$(id -un)"
```

Run that command from the checkout as the intended desktop account, so `id -un` is expanded before sudo. When already root, explicitly name the real desktop account instead. The Debian/Ubuntu installer provisions system packages; on other distributions install equivalents and use its `--skip-system` option. Installing prerequisites or changing agent configuration must stay within the user's requested scope and available permissions.

After installation, the selected release's server is `/opt/luda/current/.venv/bin/luda`. A direct graphical-session invocation can run:

```sh
/opt/luda/current/.venv/bin/luda doctor
```

## Install this skill for the current agent

From the trusted checkout, the skill helper copies the complete folder and does not install runtime or register MCP:

```sh
python3 scripts/install_skill.py --agent codex --scope user
```

Choose the actual supported client: `codex`, `claude`, `cursor`, `gemini`, or `opencode`. For project scope, use `--scope project --project /absolute/project`. `--source /absolute/skill/folder` selects an already installed complete skill folder. Read the helper's `--help` and its result for destination details. It treats identical files as a no-op and refuses differing existing content; preserve or explicitly relocate customized skills before replacement.

Use the client's documented native MCP registration for the server. Do not overwrite unrelated settings or guess that a universal MCP JSON file is consumed by every agent. Reload/reconnect the client as its documentation requires, confirm its Luda tools are exposed, then call `desktop_doctor`. An agent that supports MCP but not this skill format can use the same tool server with these instructions provided through its supported mechanism; that is integration configuration, not a new desktop backend.

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
