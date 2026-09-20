# Read-only desktop lock hints

`desktop_doctor.session_state` queries already registered screensaver services on the intended session bus. It also queries the selected GUI session's login1 `LockedHint` when the launcher supplies `XDG_SESSION_ID`. It never starts a screensaver, inhibits it, locks the desktop or attempts an unlock.

Results distinguish `locked` (reported login1 hint), `screensaver_active`, `inactive` and `unknown`. An active screensaver is not automatically an authentication lock. Inactive or missing providers do not prove that an arbitrary locker or input grab is absent. Accordingly `input_ready` is false for a reported blocking state and otherwise unknown; doctor readiness becomes false for that blocking state. These observations are sampled diagnostics, not an atomic input ownership mechanism.

This distinction follows the upstream [XFCE GetActive interface](https://github.com/xfce-mirror/xfce4-screensaver/blob/master/src/gs-listener-dbus.c) and [login1 LockedHint contract](https://github.com/systemd/systemd/blob/main/man/org.freedesktop.login1.xml).

The live test starts its own D-Bus session and a synthetic screensaver provider. It verifies missing-provider, active and inactive responses, and independently records that every received method is `GetActive`. It never locks the existing desktop. Actual login-manager lock/unlock and alternative locker integrations remain unqualified.

```sh
.venv/bin/python tests/live_session_state.py
```
