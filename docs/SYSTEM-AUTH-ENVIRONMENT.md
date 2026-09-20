# System authentication dialog: environment blocker

**AUTH-08 remains unqualified.** A read-only probe on 2026-09-20, as ordinary UID 1001 in this Linux 6.12.99 aarch64 VM, found no available real system-authentication stack. This is a finding about this image, not a claim that authentication dialogs cannot work in Linux VMs.

`scripts/probe_system_auth.py` recorded:

- `/run/dbus/system_bus_socket` does not exist. A separate read-only `busctl --system list` attempt failed with “No such file or directory”. PID 1 is `init.krun`.
- `dbus-daemon` **1.14.10-4ubuntu4.1** is installed, and session buses exist; this does not provide a system-bus polkit authority.
- `polkitd`, `pkexec`, `policykit-1`, `policykit-1-gnome`, `lxpolkit` and `mate-polkit` are not installed. No `pkexec`, `pkttyagent` or `pkaction` executable was found on PATH, and known distro authority/graphical-agent executable paths were absent.
- No matching polkit, PolicyKit or logind process was found. Twelve application/system `.policy` filenames exist under `/usr/share/polkit-1/actions`; filenames alone do not establish a working authority or agent. Their contents were not read or changed.

Upstream describes the [polkit authority on the system message bus plus a user-session authentication agent](https://polkit.pages.freedesktop.org/polkit/polkit.8.html). [pkexec uses an agent registered for the calling process or session](https://polkit.pages.freedesktop.org/polkit/pkexec.1.html). A private session bus and an ordinary GTK password fixture do not substitute for that real system-authentication path.

No authentication agent was registered, no authentication request was issued, no credentials were entered, no GUI input was sent, and no authentication policy, account, user-session settings or production dependencies were changed. In particular, the proposed `pkexec /usr/bin/true` request and explicit Cancel workflow were **not run**. There is no evidence here for identifying the real privileged-operation notice, binding the correct system dialog, cancellation behavior, caller exit or prevention of a privileged callback.

Installing/configuring a new authority, privileged execution helper and system bus would change the system-authentication environment rather than test the available one. That was outside this bounded read-only investigation. A future qualification needs a disposable image that already supplies a real authority and a separately owned graphical agent whose registration does not replace the user's existing agent; it should then observe the benign operation, explicitly cancel it and independently check the caller outcome. Window titles and ordinary protected-field support alone must not be treated as proof of system authentication.

## Reproduce the discovery

```sh
python3 scripts/probe_system_auth.py --output artifacts/system-auth/preflight.json
```

The probe returns **2 for blocked prerequisites**, or **0 for prerequisites found but not qualified**. It inspects only known distro locations and the standard system-bus socket; custom installations can differ. If that socket exists, it queries existing names through `org.freedesktop.DBus.ListNames` without calling or activating the polkit authority. It retains package versions, known executable paths, matching process names/UIDs and policy filenames, not policy contents, unrelated bus names or credentials.

The recorded ordinary-user result is `artifacts/system-auth/preflight.json`. No fake authentication fixture, runtime change or catalog-level pass accompanies this report.
