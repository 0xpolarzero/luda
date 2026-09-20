# Linux installation

Luda attaches to an existing graphical session. It does not install a desktop, start a login session, or require a particular machine manager.

## Prerequisites

- Linux, Python 3.12+, Python venv support.
- Native X11 with XTEST, XInput and RandR; an EWMH window manager. Ubuntu 24.04 with XFCE/XFWM4 and private Xvfb/XFWM4 sessions are tested.
- `xdotool`, `wmctrl`, `scrot`, `xclip`, `x11-utils`, and the X11/XInput/XTest/RandR shared libraries.
- A session D-Bus and AT-SPI2 accessibility bridge for semantic tools; system Python GI with Atspi and Pango introspection.
- Fonts for the scripts you use. The Ubuntu installer includes international and emoji fonts.

Wayland and Xwayland are unsupported. Other native X11 window managers must meet the same contracts but are not universally qualified. Accessibility depends on application providers; screenshots and pointer/keyboard tools remain the fallback where appropriate. OCR, recording and owned-browser tools have separately documented optional dependencies.

## Managed installation

From a trusted source checkout, run as your desktop account:

```sh
sudo bash scripts/install.sh /opt/luda --user "$(id -un)"
```

The installer uses Ubuntu/Debian `apt-get` for system prerequisites. On other distributions, install equivalent dependencies yourself, then use `--skip-system`. A writable user prefix can be installed without root using `--skip-system`. Account selection defaults to the invoking account; when using sudo, specify the intended desktop account explicitly. The selected account must be able to traverse the prefix. No desktop account is created or assumed.

Runtime and build dependencies are hash-locked. Installation creates an immutable versioned release, checks selected-account access, and switches `current` atomically. Existing unrelated directories are not made public. Source builds execute trusted checkout code.

In the graphical session:

```sh
/opt/luda/current/.venv/bin/luda doctor
/opt/luda/current/.venv/bin/luda
```

The second command serves MCP over stdio. Follow [Connect your agent](AGENT-INTEGRATIONS.md) to register this executable and install the skill for Codex, Claude Code, Cursor, Gemini CLI or OpenCode. The repository plugin invokes `luda` on PATH; the bundle builder writes the selected absolute installation path.

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

Check out the new reviewed release or commit in a clean source checkout, then rerun the same installation command from that checkout:

```sh
sudo bash scripts/install.sh /opt/luda --user "$(id -un)"
```

Use the same account, prefix and optional browser configuration as before; retain `--skip-system` when your deployment manages system dependencies. A successful install switches `current` to the new immutable release. Existing MCP processes still run their previous code: reconnect/restart clients after updating the runtime and skill.

For a separately installed skill, preserve the existing copy outside its discovery directory, then copy the new selected release. Example for Codex, run as the agent account:

```sh
luda_skill_backup=$(mktemp -d "$HOME/luda-skill-backup.XXXXXX")
mv "$HOME/.agents/skills/luda" "$luda_skill_backup/luda"
python3 scripts/install_skill.py --agent codex --scope user \
  --source /opt/luda/current/skills/luda
```

Use the [documented directory and agent name](AGENT-INTEGRATIONS.md#choose-your-agent) for other clients. Inspect and retain any personal changes in the backup. If no skill was installed, skip the backup and install it. The installer refuses to overwrite a different existing copy. A Codex plugin contains its own copied skill: use the [plugin update procedure](CODEX-PLUGIN.md#update) instead. Switching `current` does not update copied skills or plugin caches automatically.

After restarting the client, repeat the [read-only readiness checks](AGENT-INTEGRATIONS.md#confirm-it-works).

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
