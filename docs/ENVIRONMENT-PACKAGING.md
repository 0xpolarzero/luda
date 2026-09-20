# Include Luda in a Linux image

Use the same installer as a normal machine installation. It can install the runtime, register MCP tools, and install the complete skill before any desktop or agent is running. There is no Silo-specific dependency: an image builder, cloud-init script, or ordinary provisioning script can run it.

## Account known during the build

1. Provision a Linux X11 desktop (Ubuntu 24.04 with XFCE is tested), Python 3.12+, and the intended desktop/agent account with its home directory.
2. Download/check out a pinned Luda release. From that source directory, run as root, replacing `YOUR_ACCOUNT`:

   ```sh
   bash scripts/install.sh --user YOUR_ACCOUNT --agent codex --yes
   ```

   Repeat `--agent` for each client the image is intended to support, for example `--agent codex --agent claude-code`. The client executables need not exist yet. This installs Luda into `/opt/luda`, registers its tools for the selected account, and installs its skill into the selected clients' discovery directories. Account files belong to that account, not root. Use `--skip-system` when your recipe already provides the listed [system prerequisites](INSTALLATION.md#prerequisites).

3. Save the image, preserving `/opt/luda` and the account's configuration and skill directories. Do not relocate the installed Python environment: its executable paths are absolute. No build checkout is needed for later `luda setup` runs.

Do **not** use `--check-desktop` during image construction. Setup verifies configuration and executable availability without requiring a GUI. Do not bake credentials, display numbers, Xauthority cookies, session D-Bus addresses or running process IDs into the image.

## Account created at first boot

Install only the runtime during the build, selecting an existing provisioning account for the runtime access check:

```sh
bash scripts/install.sh --user BUILD_ACCOUNT --runtime-only --yes
```

After your first-boot mechanism creates the actual account and home, run as root:

```sh
/opt/luda/current/.venv/bin/luda setup --user YOUR_ACCOUNT --agent codex --yes
```

This step needs no package downloads or Node.js. It writes tools and skill for the new account. Repeat for each account and its chosen clients; do not assume one account's configuration applies to all users.

## When a VM starts

```text
Start the VM and log into its desktop
  → User authenticates/connects their agent
  → Agent discovers Luda's skill and connects its MCP tools
  → Run read-only readiness checks
  → Ask the agent to use the desktop
```

Your environment owns the desktop startup, accounts, SSH and agent authentication. Luda's default session launcher discovers one ready XFCE session for the chosen account and attaches to it. It does not start or unlock a desktop. For other session managers, see [session attachment](INSTALLATION.md#ssh-and-explicit-session-attachment).

For **Codex's built-in SSH remote-project connection**, install/authenticate Codex in the VM. The desktop app starts a Codex backend there as the SSH account, so configure Luda for that same account. The Mac is the interface; Luda controls the Linux desktop. See [official SSH setup](https://learn.chatgpt.com/docs/remote-connections#connect-to-an-ssh-host).

A local agent merely executing an `ssh` command does not automatically discover the VM's skills or MCP settings. Such a deployment needs explicit registration on the agent host, with a transport launching Luda in the VM. Keep SSH host-key verification; no public MCP listener is needed. Luda exports a portable bundle for custom integrations, but does not provision the SSH connection.

## Verify the running image

Run as the configured account:

```sh
/opt/luda/current/.venv/bin/luda-session --user "$(id -un)" -- \
  /opt/luda/current/.venv/bin/luda doctor
```

Then in the actual agent, confirm the Luda skill is discoverable and call `desktop_doctor`, `desktop_windows`, and `desktop_observe`. Repeat from another project to check account-wide discovery. This verifies more than an image build: the active desktop and actual client must both work. You can watch the agent cursor in your existing desktop viewer where supported.

## Updating an image or running machine

Build new images from a pinned release. For running machines, rerun the installer with the same account and selected agents, then reconnect them. Managed, unmodified skill copies update with the runtime; edited or conflicting client settings stop setup for review. See [upgrade and rollback](INSTALLATION.md#upgrade). Keep credentials out of image artifacts.

The optional Editor Bridge remains a separate add-on. Core installation does not include or enable it.
