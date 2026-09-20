# Include Luda in a Linux image

An image builder can make Luda available to agents in every working folder. Install the runtime once, then configure each **agent account** and chosen client. There is no universal directory that installs tools and skills for every agent and every Linux account.

Luda supplies the runtime, skill and registration instructions. Your image or deployment system supplies the desktop, accounts, session lifecycle, SSH access and client configuration.

## Build the image

1. Provide a supported [Linux/X11 environment](INSTALLATION.md#prerequisites) and create the intended desktop/agent account.
2. Check out a reviewed Luda release or commit. Install into a shared, readable prefix:

   ```sh
   sudo bash scripts/install.sh /opt/luda --user agent
   ```

   Replace `agent` with your account. The installer checks access but does not require a running graphical session during image construction. Use `--skip-system` if your image recipe already installs the system prerequisites. Keep the versioned installation layout intact; virtual environments must remain at the path where they were built.

3. As each agent account, copy the skill and register MCP using [the client guide](AGENT-INTEGRATIONS.md). To copy from the installed release instead of the checkout:

   ```sh
   python3 scripts/install_skill.py --agent codex --scope user \
     --source /opt/luda/current/skills/luda
   ```

   The helper is run from a retained build checkout. Alternatively, copy the complete installed `skills/luda` directory into that client's documented user skill directory. Preserve its references. The copy and client configuration must belong to the intended account, not root.

4. If agents will run through SSH, configure their MCP server to invoke `luda-session --user agent -- .../luda`. If the agent already inherits the ready graphical environment, use `luda` directly. Do not bake display numbers, session D-Bus addresses, Xauthority cookies or a running session's PID into the image.

## First boot and acceptance

Your integration starts/logs into the desktop. Then run Luda's doctor as the configured account and execute the three read-only checks in [Confirm it works](AGENT-INTEGRATIONS.md#confirm-it-works). Repeat from a different project directory to verify user-wide discovery. A successful image build alone does not prove that a later graphical session is ready.

For accounts created later, use your account-provisioning or first-login mechanism to install the selected clients' skill folders and MCP settings. `/etc/skel` only seeds future home directories; it does not update existing users or register tools in every client. Do not register clients the user has not selected.

Keep runtime upgrades, skill updates and agent reconnects in the deployment recipe. The `current` symlink selects a runtime release; copied user skills do not update automatically. Keep them from the same reviewed release. The optional Editor Bridge is a separate add-on and is not part of this core recipe.
