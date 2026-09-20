# Guest installation and agent discovery

Luda runs inside the Linux guest and attaches to its existing XFCE/X11 session. The SSH account must be the desktop account or root; the session launcher drops root privileges before GUI access. Installing tools does not create the desktop itself.

For an already running Silo desktop, the [explicit guest bootstrap](GUEST-BOOTSTRAP.md) composes installation, readiness and a reviewable remote configuration in one command. The individual lifecycle commands below remain available.

## Install and check

From the source checkout, provision the declared Ubuntu dependencies and install:

```sh
sudo bash scripts/install.sh /opt/luda
```

System provisioning includes `fonts-noto-core`, `fonts-noto-cjk` and `fonts-noto-color-emoji` so basic international text is visible to humans and screenshot-driven agents. These are additive distro packages; the installer does not change application or user font settings. `--skip-system` assumes equivalent font coverage was provisioned separately. See [font rendering evidence and limits](FONT-RENDERING.md).

If dependencies were provisioned separately, use `bash scripts/install.sh /absolute/prefix --skip-system`. The prefix must be a dedicated absolute directory owned by the installer account; symlink components, system roots and writable-by-others prefixes are refused. Do not install beneath a private root home if the desktop account must execute the result.

Each release virtual environment is created in its final `releases/VERSION-SOURCEHASH` directory. This matters because virtual-environment launchers embed absolute paths. Runtime dependencies are installed from `requirements.lock` with mandatory hash checking; the locally built wheel is installed without dependency resolution. Build tools are installed with hashes from the separate `build-requirements.lock`; wheel construction disables build isolation so pip cannot silently fetch a different backend. The lock currently pins setuptools 80.9.0 and wheel 0.45.1. System Python, its bundled pip, and apt packages remain supplied by the selected Ubuntu image/repositories. Wheel construction uses a private writable copy of the declared source inputs, removed before recording the installed inventory. Existing checkout `build/`, egg-info, `__pycache__` and installed Node dependencies are excluded; stale build modules and source-directory write permissions cannot contaminate this build. The original checkout is not modified. The same input list, including `uv.lock`, determines the release identity.

Release identities cover runtime, skill, plugin metadata, installer and packaged support files. A source change detected during preparation rejects that build and preserves the prior selection; build from an unchanged checkout. A successful preparation switches `current` atomically. Repeating the same source installation reuses its release after verifying recorded payloads. Reuse and rollback refuse missing or modified owned files, preserving edits and the current selection. Refreshed Python bytecode is excluded from this integrity check; this is a local consistency check, not a signature or hostile-account security boundary. Failed preparation preserves the previously selected release. An interrupted installer that could not clean up leaves its owned directory intact; a subsequent attempt archives that incomplete directory before retrying. System packages installed by apt are not rolled back.

The examples use a root-owned `/opt/luda`; run all `manage_install.py` actions as that prefix owner, including read-only `doctor` and configuration generation. For an ordinary-account-owned prefix, omit `sudo`. Generated files belong to the generating account but can be copied into the intended agent workspace. Do not run `codex plugin add` with `sudo` unless root is deliberately the Codex profile owner.

Run the guest/session diagnostic:

```sh
sudo python3 scripts/manage_install.py doctor --prefix /opt/luda --user silo-desktop
```

This checks the actual selected desktop session, display, accessibility bus and input dependencies. Missing sessions, ambiguous sessions and inaccessible authority files are errors. It does not fabricate readiness from an installed executable. The launcher waits up to five seconds for the selected session by default; `luda-session --wait 0` disables waiting and `--wait 30` is the maximum. Ambiguous sessions fail immediately. It never substitutes another account or session.

## Generate a reviewable Codex configuration bundle

```sh
sudo python3 scripts/manage_install.py config --prefix /opt/luda \
  --user silo-desktop --output /absolute/new/luda-config
```

The new directory contains:

- `config.toml.fragment`: a `[mcp_servers.luda]` entry invoking the installed session launcher and stdio server, with explicit timeouts.
- `.agents/skills/luda/SKILL.md`: the bundled agent instructions.
- `README.txt`: placement and verification steps.

Existing files are never overwritten. The example defaults to Codex running inside the guest. For the Mac app using an available SSH executor, add `--placement remote` and merge the fragment into the host Codex profile/project configuration that owns that executor, checking for an existing `mcp_servers.luda` entry. Registering only in the guest does not configure the host profile. Place the skill in the guest workspace's `.agents/skills/luda`, or the agent account's `~/.agents/skills/luda`. A project configuration belongs in `.codex/config.toml`; user configuration belongs in `~/.codex/config.toml`. Codex's project trust rules may affect project configuration loading. See the official [MCP documentation](https://developers.openai.com/codex/mcp) and [skill discovery documentation](https://developers.openai.com/codex/skills).

These executable paths are guest paths. They must execute on the guest side of the remote connection; copying them into a host-local MCP configuration does not create an SSH transport. After reconnecting/restarting Codex, verify that the Luda skill is listed and that `desktop_doctor` and `desktop_observe` reach the intended desktop. A fresh Mac Codex SSH onboarding session is not qualified by this Linux-only installation test.

This repository supplies guest installation/configuration helpers, not an implemented Silo UI/provisioning adapter. Silo must still wire the lifecycle into its own APIs and configuration ownership model. For that integration, the required lifecycle is: provision desktop and dependencies, install a release, run readiness, register the reviewed guest-side MCP entry and skill, then open a fresh agent connection. Registration is kept explicit so an installer cannot silently replace unrelated agent configuration.

## Tool approval and SSH placement

For unattended sandbox tasks, generate the bundle with `--tool-approval approve`. This explicitly preauthorizes Luda's tools in that profile. `writes` asks before mutations, `prompt` asks for every tool, and the default `auto` leaves the client policy in control. A noninteractive client with policy `never` can otherwise discover/read the desktop but reject every mutation; the fresh-agent evaluation reproduced this configuration distinction.

Use `--placement local` (default) when Codex itself runs inside the guest. For a host-side Codex configuration intended to use the selected SSH executor, `--placement remote` emits `experimental_environment = "remote"`; executable paths remain guest paths. This follows the current official [MCP configuration reference](https://learn.chatgpt.com/docs/config-file/config-reference). Remote placement is experimental, and the actual fresh Mac SSH onboarding flow still requires end-to-end testing. Generating the fragment alone does not qualify it.

The generated server is `required = true`, so a client supporting this option reports startup failure instead of silently continuing without Luda. These configuration fields and the fresh local agent test were checked with Codex CLI 0.155.1.

## Rollback and uninstall

Select a previously completed release without rebuilding it:

```sh
sudo python3 scripts/manage_install.py rollback --prefix /opt/luda --release VERSION-SOURCEHASH
```

Release IDs are listed in `/opt/luda/.luda-install.json`. Rollback changes future launches; it does not replace an already running server. Stop/reconnect the client deliberately when selecting a different release.

```sh
sudo python3 scripts/manage_install.py uninstall --prefix /opt/luda
```

Uninstall removes the managed `current` link and installed files that still match their recorded hashes or symlink targets. Modified or unknown files, interrupted-build archives and external agent configuration are preserved. The result reports retained modified releases. Stop clients before uninstalling: removing files beneath a running process is not a supported hot-uninstall mechanism. If an agent configuration or copied skill was registered separately, remove its Luda entry explicitly while preserving other entries.

Installation logs can contain package names and paths. The installer does not collect desktop screenshots, input text, tokens or authority cookies. Its source checkout must be trusted: package builds execute source-controlled build code.

The session launcher changes working directory **after** dropping privileges: it uses the selected desktop account’s home, or `/` if that home is unavailable. This prevents root SSH sessions from leaving MCP in an inaccessible `/root`. Use `luda-session --cwd /absolute/workspace -- ...` when the command needs a particular working directory; an inaccessible explicit directory is an error. Relative executable paths are resolved before this change, while relative command arguments are interpreted from the selected working directory. The launcher does not create a missing home directory.
