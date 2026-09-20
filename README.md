# Luda

A standalone plugin, skill, and MCP toolset for agents operating graphical Linux machines. Luda controls an existing desktop; it does not provision a desktop or require a sandbox manager, cloud service, or model API.

## Install and connect

Supported baseline: Linux with Python 3.12+, native X11, an EWMH window manager, and the dependencies in [installation](docs/INSTALLATION.md). Ubuntu 24.04 with XFCE/XFWM4 is tested on ARM64 and AMD64. Native Wayland and Xwayland are unsupported and rejected before desktop input.

From a trusted checkout, as your desktop account:

```sh
sudo bash scripts/install.sh /opt/luda --user "$(id -un)"
/opt/luda/current/.venv/bin/luda doctor
python3 scripts/build_plugin.py --prefix /opt/luda \
  --marketplace-root "$HOME/.local/share/luda-marketplace"
```

Run the diagnostic and agent in the graphical session so they inherit `DISPLAY`, session D-Bus and X authorization. The generated plugin uses the installed executable directly. For SSH or another account, see [explicit session attachment](docs/INSTALLATION.md). Register the generated [plugin and skill](docs/CODEX-PLUGIN.md) in the agent that will use them.

## Use

1. Run `desktop_doctor`, list windows, and select the intended one.
2. Inspect controls; prefer semantic desired-state actions and verified text editing.
3. When controls are inaccessible, observe the desktop and use the returned screenshot coordinates.
4. Verify the application's resulting state. After uncertainty, inspect before retrying input.

Core tools cover screenshots, windows/workspaces, pointer and keyboard input, Unicode/multiline text, accessibility controls, clipboard paste, waits, cancellation and input recovery. Optional tools provide owned-browser interaction, OCR, image matching and recording. See the generated [tool reference](docs/TOOLS.md) and [agent skill](skills/luda/SKILL.md).

## Support and testing

[Validation](docs/VALIDATION.md) separates demonstrated behavior, product defects, test-harness failures and unsupported environments. The supported backend and provider limitations are explicit; successful dispatch is not proof of task completion. The existing acceptance inventory is frozen rather than a promise to support every desktop configuration.

```sh
uv sync --frozen --extra test
.venv/bin/python scripts/qualify.py
LUDA_ISOLATED_TEST_DISPLAY=1 xvfb-run -a \
  -s '-screen 0 1440x900x24 -nolisten tcp' dbus-run-session -- \
  .venv/bin/python scripts/headless_tests.py
```

Live tests use synthetic documents and independent widget/file/DOM readback. Tests against a shared desktop must hold `/tmp/luda-live-tests.lock` throughout. CI also runs private X11 sessions. [Backend support](docs/BACKEND-SUPPORT.md) and [semantic contracts](docs/SEMANTIC-CONTROLS.md) describe the boundaries.
