# Private real polkit cancellation: scoped protocol evidence

AUTH-08 now has an actual private authority/pkexec cancellation observation,
separate from the existing distro-agent environment blocker. **It remains
release-unqualified.** The successful dialog is an explicitly custom cancel-only
agent backed by real polkit, not a fake ordinary password field and not the GNOME
agent's password dialog.

## What actually ran

Pinned Ubuntu ARM64 packages supplied polkitd/pkexec 124-2ubuntu1.24.04.4,
libpolkit-agent and GI metadata of the same version, and
policykit-1-gnome 0.105-7ubuntu5. Package SHA256 values were checked against the
Ubuntu archive's APT metadata and are fixed in the runner. No package was globally
installed and no maintainer scripts were executed. In particular, the pkexec
package ships mode0755 and its postinst sets root:root4755; the runner reproduces
only that mode change inside its private tmpfs-backed `/usr` overlay.

A root launcher creates mount, PID and network namespaces, private tmpfs-backed
`/usr`, `/etc` and `/var` overlays, and a private `/run` system-bus socket. It starts
real dbus-daemon and polkitd, with a namespace-only daemon account. There is no
service activation configuration on this private bus. The graphical session,
custom agent and MCP run as existing ordinary UID1001 in owned Xvfb/D-Bus/XDG
state. Namespace PID1 exit destroys the namespace descendants. A 45-second outer
watchdog kills only the launched process group on timeout.

This is **not** a user-namespace isolation claim: multi-UID mapping was unavailable
because `newuidmap` was absent. The launcher uses explicit root mount/PID/network
isolation and then drops GUI/client privileges. The shell helper refuses direct
execution unless it is PID1 and its mount/network namespace IDs differ from the
launcher's. Existing host polkit account/group identities cause a preflight refusal
rather than being repurposed.

The unmodified GNOME agent really attempted registration and failed:
“Unable to determine the session we are in: No session for pid …”. The authority
also reported its missing login monitor. This VM has no real login session/logind,
so the stock session agent remains **blocked**, not passed.

## Authority-backed custom agent and GUI Cancel

The small test agent implements the documented authentication-agent D-Bus
interface. It registers the exact owned UnixProcess PID/start/UID with the real
private authority. Before accepting a request it resolves the authority's unique
bus owner and PID, checks the method sender, action
`org.freedesktop.policykit.exec`, and the authority-supplied caller/subject PIDs.
Those must match its own live child and registered process. The child argv is
independently checked as exactly `pkexec --disable-internal-agent /usr/bin/true`.
No arbitrary program or authentication decision is accepted.

The authority does not forward the `program` detail to this agent; it forwards
`polkit.caller-pid` and `polkit.subject-pid`. The program label therefore comes from
the checked owned caller argv, while the displayed authentication message comes
from the authenticated authority request. The screenshot visibly says that
running `/usr/bin/true` as superuser requires authentication. Window title alone
was never used as proof of privilege.

Public Luda tools listed and activated the owned agent's exact native PID/window,
observed the dialog, inspected Cancel and invoked that observed action. The custom
agent has no password entry or Approve control and never sends an authentication
response. Cancel returns the protocol's cancellation error to the authority.
The independent results were:

- One real `BeginAuthentication` and one GUI Cancel.
- `pkexec` exit **126**, with “Request dismissed”; `/usr/bin/true` would return 0.
- Authority log records authentication failure, then agent unregistration.
- No credential input and no authorization response; the dialog disappeared.

The custom agent's literal zero counters describe the intentionally absent code
paths, not a general credential-monitoring mechanism. D-Bus sender/PID binding is
harness evidence; production Luda gained no privileged-dialog classifier or hidden
policy. This does not qualify GNOME's password dialog, successful authentication,
PAM, privilege elevation or real user accounts.

## Evidence and reproducibility

The final reusable run `run-1789900736406239026` passed in **3.460 seconds**.
Its source fingerprint stayed
`1ebbf0a4da16d8b2092cbfa655f2e4952856570bf50a4dbd55b6c7cbb4dbc858`.
Host account/group files, policy trees, pkexec/authority paths and system-bus
presence matched their pre-run snapshots. Outside the namespace, no polkit
account, authority/pkexec executable or system-bus socket was introduced.
Three runner contracts cover changed/symlink packages, ignoring unpinned extras,
and refusing direct namespace-helper execution before mutation.

[Retained evidence](../tests/evidence/private-polkit/README.md) includes every
preliminary attempt: stock agent blocked; missing package-postinst setuid mode;
overly strict expectation of a non-forwarded `program` field; corrected actual
cancellation; and final reusable runner. Original failures are not overwritten.
Provider GLib warnings and the missing `admin` group warning remain in the logs.
The final screenshot SHA256 is
`59bcab11fa5dcb3c372b1b6109d09e6c118d065ce7df75ce4ab825e8504780ff`.

On this supported Ubuntu24.04 ARM64 test VM, download the exact packages into a
new test directory with `apt-get download` (not install):

```sh
apt-get download polkitd=124-2ubuntu1.24.04.4 pkexec=124-2ubuntu1.24.04.4 \
  libpolkit-agent-1-0=124-2ubuntu1.24.04.4 \
  gir1.2-polkit-1.0=124-2ubuntu1.24.04.4 policykit-1-gnome=0.105-7ubuntu5
# Root only, fresh output created automatically; no host policy/service changes.
.venv/bin/python scripts/private_polkit_tests.py --packages /absolute/test-directory
```

The runner uses already provisioned GTK/AT-SPI/Xvfb/XFWM and Luda dependencies;
it neither downloads packages nor enables a host service. It is deliberately
separate from ordinary application CI and the production installer.

Primary contracts: [polkit architecture](https://polkit.pages.freedesktop.org/polkit/polkit.8.html),
[pkexec cancellation exit status](https://polkit.pages.freedesktop.org/polkit/pkexec.1.html),
and [authentication-agent D-Bus interface](https://github.com/polkit-org/polkit/blob/main/docs/polkit/docbook-interface-org.freedesktop.PolicyKit1.AuthenticationAgent.xml).
