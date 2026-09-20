# Luda

Local Linux desktop control for agents. Luda attaches to the XFCE/X11 desktop already visible in a Silo microsandbox and exposes typed MCP tools plus an agent skill. It runs entirely inside the guest, without a model API, cloud worker or second VM.

**Under active development; not yet release-qualified.** The [346-case acceptance catalog](docs/REQUIREMENTS.md) defines the target, and [validation status](docs/VALIDATION.md) distinguishes working features from remaining gaps. Successful input dispatch is never presented as proof that an application completed the intended task.

## Use it

For an existing running Silo desktop, the [guest bootstrap](docs/GUEST-BOOTSTRAP.md) composes installation, readiness checks and a remote Codex configuration/skill bundle in one command. For host Codex, the [VM-specific SSH plugin builder and explicit profile registration](docs/HOST-REGISTRATION.md) package the tools and skill together. Each VM has its own resolved MCP server name. Native Silo UI integration and Mac end-to-end acceptance remain in progress.

For manual installation on an existing Ubuntu 24.04 XFCE/X11 desktop:

```sh
sudo bash scripts/install.sh /opt/luda
sudo python3 scripts/manage_install.py doctor --prefix /opt/luda --user silo-desktop
sudo python3 scripts/manage_install.py config --prefix /opt/luda \
  --user silo-desktop --placement remote --output /absolute/new/luda-config
```

Run these commands inside the guest checkout. `sudo` is needed for management of this root-owned prefix; the graphical launcher drops to `silo-desktop`. The example generates an experimental remote-executor fragment for a host Codex SSH profile. If Codex itself runs inside the guest, use `--placement local` instead. Generation alone does not register the server or skill; follow the placement instructions in the bundle.

The installer creates versioned releases and switches `current` atomically. The configuration command generates a guest-side MCP fragment and discoverable skill without overwriting existing agent settings. See [installation, registration, rollback and uninstall](docs/INSTALLATION.md). An [installable Codex plugin](docs/CODEX-PLUGIN.md) packages the MCP registration and skill together. Fresh Mac Codex SSH onboarding still needs end-to-end qualification; guest installation alone does not prove host-side discovery.

## Agent workflow

1. Check `desktop_doctor`, then list windows and activate the intended one.
2. Inspect its controls. Use `desktop_type` for verified insertion or whole-field replacement where exact text access is supported, and desired-state operations for selection, checkboxes, expansion and values.
3. When accessibility is unavailable, observe the screenshot and use its coordinates. The same click/hover tools handle owned context menus and submenus.
4. Read back or wait for the intended state. After an uncertain result, inspect before repeating input.

The [tool reference](docs/TOOLS.md) is generated from actual MCP declarations. The [skill](skills/luda/SKILL.md) explains targeting, text and recovery. Other capabilities include window/workspace management, cross-window drag, table-row selection, clipboard paste, shared pause/resume and explicit input cleanup recovery. Pointer and key dispatch still require application-specific verification.

## Develop and test

```sh
uv sync --frozen --extra test
.venv/bin/python -m unittest discover -s tests -p 'test_*.py'
LUDA_ISOLATED_TEST_DISPLAY=1 xvfb-run -a \
  -s '-screen 0 1440x900x24 -nolisten tcp' dbus-run-session -- \
  .venv/bin/python scripts/headless_tests.py
```

The fresh-display runner exercises native controls, actual MCP, cancellation, shared pause, controller crashes and X-server replacement. Other live suites cover GTK3, Qt5, GTK4, Chromium, [Firefox](docs/FIREFOX-QUALIFICATION.md), [Electron](docs/ELECTRON-QUALIFICATION.md), native applications and installation. They use synthetic documents and independent widget/file/DOM readback. See [qualification methodology](docs/QUALIFICATION.md) and the [optional qualification matrix](docs/QUALIFICATION-MATRIX.md) for failures as well as passes. The installer also provisions international and emoji [fallback fonts](docs/FONT-RENDERING.md).

Tests using the existing guest desktop must hold the shared lease throughout their lifetime:

```sh
flock /tmp/luda-live-tests.lock /absolute/luda/.venv/bin/luda-session -- \
  /absolute/luda/.venv/bin/python /absolute/luda/tests/live_backend.py
```

`artifacts/` is ignored by Git. CI runs unit and isolated X11 workflows on Ubuntu AMD64; local guest tests run on ARM64. Neither substitutes for a fresh Silo VM acceptance run.

## Contracts and scope

Window identities include process lifetime and an X-resource generation token. Screenshot coordinates expire and are revalidated against display topology, geometry, focus, menus and the topmost surface. Semantic handles are scoped to an observed window and expire; private full-name fingerprints detect changes beyond displayed name prefixes. Provider reuse of an identical identity remains a limitation; see the [semantic contract](docs/SEMANTIC-CONTROLS.md). Input is serialized across cooperating clients, and `desktop_control` can pause their mutations. Owned injectors provide bounded cleanup after interruption; unproven cleanup remains blocked, and old cleanup does not touch a replacement X server.

X11 does not provide exclusive ownership against human viewer input. Clipboard paste replaces CLIPBOARD, leaves PRIMARY alone and may trigger a terminal paste dialog. Direct typing verifies exact text where supported; browser and toolkit differences remain under qualification. Native Wayland and modern Xwayland are explicitly rejected before desktop requests; see the [backend boundary and live refusal evidence](docs/BACKEND-SUPPORT.md). Rich clipboard formats, OCR and browser DOM automation remain outside the production implementation. Read the [architecture and behavioral contracts](docs/DESIGN.md) before embedding Luda as a release component.
