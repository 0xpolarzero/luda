# Silo integration source review

Read-only review of `0xpolarzero/silo` commit
`777e1090d5e998059758160912138228ba98378d` (2026-09-20). No Silo files or host
configuration were changed. This identifies implementation hooks, not a tested
Mac integration.

## Existing hooks

All links below pin the inspected Silo commit.

- [desktop.rs](https://github.com/0xpolarzero/silo/blob/777e1090d5e998059758160912138228ba98378d/app/SiloUI/src-tauri/src/desktop.rs):
  `configure_with` embeds the guest desktop setup/service sources when adding the
  desktop. Its `guest` helper invokes the bundled runtime's `exec` with root,
  no TTY, explicit timeout and a script. Existing public Tauri actions expose
  desktop status/start/stop/restart, not arbitrary extension installation.
- [runtime.rs](https://github.com/0xpolarzero/silo/blob/777e1090d5e998059758160912138228ba98378d/app/SiloUI/src-tauri/src/runtime.rs):
  creation and configuration/update paths call `desktop::configure_with`
  (around lines 2838, 3044 and 3129). This is the relevant product integration
  point; merely altering a guest helper cannot make Silo invoke it automatically.
- [setup-desktop.sh](https://github.com/0xpolarzero/silo/blob/777e1090d5e998059758160912138228ba98378d/app/SiloUI/src-tauri/guest/setup-desktop.sh):
  installs Xfce and pinned KasmVNC, creates the `silo-desktop` account, writes an
  X startup script running `dbus-run-session -- xfce4-session`, installs
  `/usr/local/bin/silo-desktop`, records metadata and boots the desktop. It does
  not install Luda. Its dependency set is smaller than Luda's installer set.
- [desktop-service.py](https://github.com/0xpolarzero/silo/blob/777e1090d5e998059758160912138228ba98378d/app/SiloUI/src-tauri/guest/desktop-service.py):
  root management supports `status`, `start`, `stop`, `restart`, `boot` and
  autostart. `status` returns installed/state/version/user/display metadata.
  `connection` returns viewer credentials and is unnecessary for Luda; an adapter
  must never read it. Luda should continue discovering the actual XFCE session,
  not copy `DISPLAY=:1` and assume a D-Bus/authority environment.
- [editor.rs](https://github.com/0xpolarzero/silo/blob/777e1090d5e998059758160912138228ba98378d/app/SiloUI/src-tauri/src/editor.rs):
  Silo's local editor handoff prepares root SSH aliases, a private client key and
  pinned host key; configuration uses a ProxyCommand through its bundled runtime.
  `prepare_private_transport` supports internal isolated connections without
  changing user SSH configuration. These are Rust internals, not a public CLI
  API a Luda shell script can safely call or reproduce.
- [ssh_connection.rs](https://github.com/0xpolarzero/silo/blob/777e1090d5e998059758160912138228ba98378d/app/SiloUI/src-tauri/src/ssh_connection.rs):
  the UI's SSH connection action produces an explicit root command or exports a
  selected identity, with different local/remote-host endpoint handling. An
  integration should consume Silo's selected connection, not discover keys or
  assume an alias/port. Luda needs neither viewer credentials nor host key files.
- [linux-desktop-viewer.tsx](https://github.com/0xpolarzero/silo/blob/777e1090d5e998059758160912138228ba98378d/app/SiloUI/src/desktop/linux-desktop-viewer.tsx):
  consumes desktop status/actions. `desktop.rs::public_status` projects a fixed
  desktop-only schema, so a tools-readiness badge needs explicit Silo-side schema
  and UI work rather than adding fields only to a guest response.

Silo's [desktop documentation](https://github.com/0xpolarzero/silo/blob/777e1090d5e998059758160912138228ba98378d/docs/SiloUI-DESKTOP.md)
explicitly says agent harnesses/plugins/MCP servers are not installed. Therefore
“GUI plus Luda automatically” is a missing product integration, not an existing
feature awaiting only an external test.

## Bounded repo-local adapter recommendation

A useful next deliverable can be implemented and tested entirely in Luda without
changing Silo or running macOS: an **explicit guest bootstrap command**, invoked
inside the already selected Silo guest, with caller-supplied trusted Luda source,
prefix and fresh output directory.

It should perform only these composed steps:

1. Read `/usr/local/bin/silo-desktop status` with a deadline; validate the supported
   metadata version, installed desktop and expected account. Report a stopped or
   starting desktop separately. Do not start/stop the desktop as an implicit side
   effect or read viewer `connection` data.
2. Invoke the existing versioned Luda installer with explicit ownership and
   dependency policy. Reuse its locks, hashes, rollback and interruption behavior.
   Require a supplied local source/release; do not invent a mutable download URL.
3. Run the existing session-aware doctor and report desktop state separately from
   tools readiness. Missing/stopped desktop must not erase successful installation
   metadata or masquerade as a ready tool server.
4. Generate a fresh remote-placement config/skill bundle and optionally a plugin
   bundle from matching source. Return machine-readable artifact paths, selected
   release and readiness. Preserve unrelated configuration; do not edit host or
   guest Codex registries automatically.

Tests can cover missing Silo helper, unsupported status version, stopped desktop,
wrong account, installation failure preserving current, missing dependencies,
repeated invocation with fresh output, and exact remote-placement artifacts.
A live run can use an existing owned guest or private command fixture; neither
would constitute a fresh microsandbox provisioning test.

This adapter reduces manual guest glue but does **not** finish one-click Silo
onboarding. Automatic invocation after GUI installation/update, choosing the
Mac Codex configuration/profile, transferring/registering the bundle, separate
health UI and user-facing upgrade/reconnect behavior still require Silo changes
and real Mac acceptance. Do not reimplement its private SSH bridge, add a second
SSH key flow, or claim an undocumented app command is supported.
