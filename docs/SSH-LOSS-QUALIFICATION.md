# Actual local SSH transport loss

`tests/live_ssh_loss.py` supplies bounded **FAULT-06** evidence with a real OpenSSH connection, complementing the separate [MCP stdin EOF test](MCP-DISCONNECT-QUALIFICATION.md). It drives public Luda MCP tools over SSH against an ordinary-user private desktop, then kills the owned SSH client after independent evidence that mutation has started. Both network transport directions disappear; this is not merely closing stdin while continuing to drain the server's stdout.

## Disposable infrastructure

The VM initially had no OpenSSH client/server executables or packages. Official Ubuntu packages were downloaded and extracted, without installation, maintainer scripts or global SSH service/configuration changes:

- `openssh-client`, `openssh-server`, `openssh-sftp-server`: **1:9.6p1-3ubuntu13.19**, arm64.
- `libwrap0`: **7.6.q-33**, arm64, resolving the only missing shared library.
- Executable report: **OpenSSH_9.6p1 Ubuntu-3ubuntu13.19, OpenSSL 3.0.13 30 Jan 2024**.

The extra library comes from the private extraction's `usr/lib/aarch64-linux-gnu` through the test process's `LD_LIBRARY_PATH`. No `sshd` account or `/run/sshd` directory was added: configuration validation and same-UID SSH operation both work with a non-root daemon here. `scripts/probe_ssh_transport.py` reproduces the no-listener configuration check using only a newly generated temporary host key.

Each full run creates a private Xvfb/D-Bus/XFWM/XDG session and a UID 1001 sshd listening **only on 127.0.0.1 at a temporary high port**. Host/client keys are generated in an owned 0700 temporary directory. The client pins the generated host public key, disables agent use, and uses only its explicit identity and owned known-hosts file. The daemon accepts only the current user and the generated public key; its forced command launches the private MCP endpoint. Password/PAM authentication, root login, agent/TCP/X11 forwarding, tunnels and user SSH rc execution are disabled.

The first connection preflight was refused because OpenSSH `StrictModes` rejected the world-writable `/tmp` ancestor. Setting `StrictModes=no` **only in this disposable config**, while retaining the private 0700 directory and explicit authorized-keys file, allowed the generated-key connection. The initial refusal is retained in the evidence; this setting is not a production recommendation. No existing credentials, host keys, authorized-keys files or user SSH configuration were read by the test client setup.

Private keys, authorized keys, pinned hosts and daemon configuration are removed with the temporary directory. Evidence retains only versions, package hashes, public fingerprints, synthetic fixture state, process identities and cleanup outcomes.

## Independent effects and results

The keyboard case requests twenty `a` presses. A separate Xlib `XQueryKeymap` oracle confirms physical key-down before the pending MCP response, then the harness sends SIGKILL to the SSH **client**, not the remote server or its helpers. The remote server and native helper identities are tracked by PID plus process start time. Their disappearance and independent key/button release are required.

The second case invokes a real GTK button. Its callback persists `started=1, completed=0` and waits on an application-owned gate. The harness kills the SSH client only after that state exists, then releases the gate. The already-delivered callback completes once **after transport loss**. That late effect is expected: disconnect is not undo.

Fresh SSH/MCP sessions have no old operation history and leave the application unchanged before new explicit input. Only a separately requested `z` and separately requested button invocation produce additional effects. Lost requests are not replayed by the harness.

All ten assertions passed in the initial full run and one final immutable-source confirmation. The final run, from commit `cfe6220`, took **5.150 seconds**:

- Key release, remote server exit and helper disappearance: **0.279 seconds** after transport loss. One of twenty requested characters had arrived; no MCP response was received for the interrupted key request.
- Gated callback: completed exactly once after disconnect; remote server/helpers disappeared in **0.111 seconds**. A fresh session did not replay it; explicit new invocation alone incremented the count to two.
- Both intentionally killed SSH clients exited with **-9**. Remote process disappearance is verified independently; no remote zero exit code is invented after output loss.
- No forced remote cleanup was needed. Outer cleanup found **zero tagged survivors**. The listener exited and generated key directories were removed.
- Before/after source fingerprints matched: `0e223dcda30c41950ff44ad9ef2836de8dd32799fc793283ad3d575552c7cd2a`.

Evidence lives under `artifacts/ssh-loss/`: `packages.json`, `preflight-ordinary.json`, `first-auth-refusal.txt`, `attempt-1/` and `final/`. The refusal file is explicitly a transcription of the first preflight's terminal output. No Luda runtime fix was required.

## Reproduce

Extract test dependencies from the configured official distro repositories into a new private directory; do not install them:

```sh
mkdir -p /tmp/luda-openssh-packages
cd /tmp/luda-openssh-packages
apt-get download openssh-client openssh-server openssh-sftp-server libwrap0
for package in ./*.deb; do dpkg-deb -x "$package" extracted; done
```

From a writable Luda checkout, run as the ordinary desktop account:

```sh
.venv/bin/python tests/live_ssh_loss.py --package-root /tmp/luda-openssh-packages/extracted
```

A root-owned checkout needs an ordinary-user-writable `artifacts/ssh-loss` parent, as other live suites do. The test creates the private session itself, uses fresh artifact directories by default and has a 100-second outer watchdog. It downloads nothing during execution.

Limits: local TCP transport teardown from SSH-client death, one same-UID forced-command configuration and two controlled mutation phases. This does not qualify network blackholes, half-open timeouts, remote host crashes, root/PAM login, multiplexed connections, arbitrary delayed application callbacks, or Mac Codex SSH onboarding. It is distinct from both stdin-only EOF and an end-to-end product integration on macOS. Catalog-level qualification is not inferred from this bounded experiment.
