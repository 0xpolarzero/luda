# Generated host plugin over real private SSH

`tests/live_host_plugin_ssh.py` exercises the generated per-VM MCP commands through a real loopback SSH transport, rather than treating Codex registry metadata as proof that a server starts. It requires root for its isolated account-switching fixture, already provisioned desktop dependencies, and separately extracted official OpenSSH packages. It does not install an SSH service, modify global SSH/authentication configuration, unlock accounts or consult user identity keys.

The fixture builds a fresh installed release from its worktree using the locked installer (no apt). It creates two private ordinary-UID XFCE/Xvfb/D-Bus sessions, using existing `daemon` and `nobody` accounts with private HOME/XDG/Xauthority, and generates distinct plugin identities/server keys/SSH aliases. Its synthetic prefix and SSH configuration paths contain spaces, quotes and literal shell substitution syntax to exercise argument preservation.

One unprivileged private sshd, authenticated only with newly generated keys, listens on `127.0.0.1`. The existing desktop account's sudo permission supplies a test-only bridge: a root-owned forced-command wrapper accepts only the two byte-exact generated remote commands, then executes them unchanged. Other SSH commands must fail with exit 64. This avoids changing the locked root account and global privilege-separation setup. It is not evidence for Silo's actual root SSH authentication route. The generated `luda-session` then selects the intended unique desktop session and drops to its account as normal.

For each alias the fixture performs MCP initialize, tools/list, doctor, windows and screenshot observation. The independent oracles are the distinct UID/display reported by the actual session launcher, the owned GTK fixture PID in the window list, and unchanged widget text/events. Both aliases use the same loopback daemon and physical Linux VM; they are explicit stand-ins for two VMs, not two actual microsandboxes. Registration/cache behavior has separate unit/CLI evidence. No fresh Mac, Silo editor SSH discovery or Codex agent-loaded skill claim follows from this test.

Run with a dependency-equipped Python interpreter:

```sh
python tests/live_host_plugin_ssh.py --output /workspace/FRESH_TEST_DIRECTORY --package-root /tmp/luda-openssh-packages/extracted
```

The fixture retains its fresh install, generated plugin files, private keys and logs for inspection; delete that owned test directory explicitly when finished. Process cleanup is limited to owned process groups and its unique invocation token, never all processes belonging to an account. It never needs the shared GUI lease because all desktops are private.

## Preserved discovery and correction

The first attempt (`/workspace/luda-host-plugin-ssh-run-1/`) stopped before SSH startup because its session child used system Python without MCP dependencies. The harness was corrected to use its dependency-equipped caller interpreter.

The second attempt (`/workspace/luda-host-plugin-ssh-run-2/`) authenticated successfully and executed the literal quoted launcher path, but MCP initialization failed. After privilege drop, `luda-session` retained the inaccessible SSH working directory; FastMCP's dotenv discovery raised `PermissionError` for `.env`. Normal root SSH starting in mode0700 `/root` has the same issue. Runtime fix `44f53ea` selects an accessible account home after privilege drop, falling back to `/` when the default home is unavailable; explicit inaccessible `--cwd` requests are refused. The third attempt uses that fix. The original failure logs remain intact.

## Passing local result

The corrected third run passed for both aliases. `alpha` resolved server key `ld-00000000000000000000000000000001` to UID 1/display `:140`; `beta` resolved key `ld-00000000000000000000000000000002` to UID 65534/display `:141`. Both discovered 32 tools, returned ready doctor results, found their intended fixture PID through their separate display, produced a screenshot, and left the widget text/events unchanged. Both refused a command outside the exact forced-command allowlist. Literal shell syntax stayed literal, with no injection marker created.

Raw logs and result: `/workspace/luda-host-plugin-ssh-run-3/`. The tested base was main `6c2e18d` plus runtime fix `44f53ea` and the new fixture; the result includes the complete source fingerprint and records `source_unchanged=true`. Source digest: `7eed88dda3a54d6c09f87e46b6f73434a1372a7d24e79632cc6e73db2cd3a6dc`. No shared desktop activity occurred. Subsequent process inspection found no surviving session/fixture processes for the two test accounts. The runtime cwd bug is corrected by independent runtime tests as well as this actual SSH rerun.
