# Installed startup without external networking

SHIP-05 now has a real denied-network runtime experiment. On 2026-09-20, an
ordinary UID1001 private Xvfb/XFCE/D-Bus session ran installed release
`0.1.0-1fd079f0094942e5` (the runtime already qualified at `63c5ac7`) inside a
separate Linux network namespace. All 47 installed Python modules matched the
release's recorded file hashes before MCP startup. The probe imports the installed
package using `-I`, then launches the installed `luda-session` and `luda` entrypoints.
It does not substitute the current checkout runtime.

The root harness uses `unshare --net` and then drops to the selected ordinary
account before starting any GUI process. No host interface, route, firewall,
shared desktop, credential file or authentication setting is changed. The child
namespace has only down loopback, no IPv4 routes and no external interfaces.
A host-loopback listener is independently reachable before isolation; connection
to it inside the namespace fails with ENETUNREACH (101). Connections to the IPv4
TEST-NET address `192.0.2.1` and IPv6 documentation address `2001:db8::1` fail with
101 and EADDRNOTAVAIL (99), respectively. The namespace and canaries are checked
again after the workflow. Unix sockets remain available for X11 and D-Bus.

Within that boundary, actual stdio MCP initialization and tool listing succeeded.
Doctor reported ready, window enumeration found the owned GTK fixture, semantic
text replacement matched an independently persisted multiline/Unicode/tab string,
a button changed its independent counter exactly once, and the returned PNG
matched its coordinate metadata. The server ran without model/vendor credentials
in its fresh allowlisted environment. No vendor login, startup download or external
network access was required for these operations. Optional browser **launch** and
cloud-agent inference were not tested; capability discovery is not browser launch.

The final run retained unchanged fixture hashes, seven public tool responses after initialization and tool listing, and a successful stage-cleanup receipt: 51 owned process
identities observed, no survivors, 0.049 seconds cleanup. There were two successful
local runs: the second added metadata-only operation tracing and before/after
fixture hashes. The first attempt failed before GUI/MCP because the harness had
not allowed IPv6's legitimate no-address errno99. Its trace and successful cleanup
receipt remain in `first-attempt.json`; it is not counted as a runtime pass.
Two unit contracts additionally reject a reachable canary, unchanged namespace,
extra interface, nonempty routing table, and mere connection timeout.

## Reproduce

Prepare an already installed release and the existing native test dependencies
(`unshare`, `runuser`, Xvfb/xauth, XFCE session/window manager, D-Bus, system GTK3
and AT-SPI). Use a fresh output path and an explicit ordinary desktop account:

```sh
sudo python3 tests/evidence/offline-startup/run.py \
  --release /opt/luda/current \
  --user silo-desktop \
  --output /workspace/offline-proof-new
```

A host that refuses private network namespaces cannot pass this fixture: it fails
with retained stage logs and does not fall back to simulated denial. The harness
uses the existing bounded CI subreaper for descendant cleanup. Its limits include
SIGKILL of that supervisor and kernel/VM failure; it cannot undo application
changes already performed. The fixture deliberately uses a synthetic document.

[Retained result files](../tests/evidence/offline-startup/result/) include the
network proof, pinned-runtime hashes, public operation metadata, source hashes,
result and cleanup receipt. The source runner and probe live in the same evidence
directory. Full local logs and the synthetic screenshot remain under
`/workspace/luda-offline-proof-3/`. This is a bounded installed Linux runtime test,
not fresh Mac/Silo provisioning or a catalog-level release qualification.
