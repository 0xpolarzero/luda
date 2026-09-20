# Source-informed focus mechanism probes

Private Xvfb/XFWM, GTK3 applications, explicit local test UID 0. No shared `:1`
desktop was used. This is mechanism evidence, not public-tool or production
qualification. Runtime revision and exact source hashes are in `summary.json`.

| Case | Human typing delivered | Agent application oracle |
| --- | --- | --- |
| Private non-core events; human Shift held | 43/43 uppercase `B` | Button counter, entry lowercase `a`, popup open and Escape-close pass |
| Same private input plus minimized-window restore | 58/58 lowercase `b` | Restore and button/entry/popup sequence pass |
| Prior core-event-enabled pair control | 1/44 | Human typing is redirected after agent click |
| GTK AT-SPI Component.grab_focus | 1/18 | Human typing is redirected to agent's entry |

The successful cases also keep sampled core focus at the human window. Exact
continuous-input fixture contents detect redirected/lost characters during these
bounded tests; endpoint focus samples alone are insufficient. Concurrent actions
in different windows of the same application, different WMs, non-GTK providers,
and arbitrary application-generated dialogs are not covered by these probes.

Run the command in `tests/prototypes/isolated_focus.py` on a new private Xvfb,
selecting `normal`, `restore`, or `ax_focus`. Set `LUDA_HUMAN_SHIFT=1` for the
modifier case and `LUDA_CORE_EVENTS=1` for the old core-event control. The helper
is intentionally a research prototype, using fixed device names only because it
runs on a new disposable server; it is not the product device-ownership code.

## Why these mechanisms differ

[Xorg CheckDeviceGrabs](https://github.com/XQuartz/xorg-server/blob/0ea9b595891f2f31915538192961f3404d9ca699/dix/events.c)
uses the master's `coreEvents` flag when checking core passive grabs. XFWM installs
XI2 button grabs on its default pointer, while legacy core grabs also affect
additional core-event-enabled pointers. Disabling core events avoids that legacy
route for the tested GTK XI2 controls; legacy application delivery still needs
separate qualification.

[XFWM clientFocusNew](https://github.com/xfce-mirror/xfwm4/blob/d30886f7baf9088601775212ab62efac9e84795f/src/focus.c)
honors the EWMH `_NET_WM_USER_TIME=0` no-initial-focus request. Luda scopes that
request to the restored window and its time-owner proxy, checks generations,
then restores timestamps unless the application has replaced them. The request
is not a guarantee about every WM. Normal failures/timeouts execute cleanup;
an abrupt helper kill may leave a zero timestamp until the application updates
it. This is a window property, not a grab or physical-device modification.

[GTK3's accessibility focus implementation](https://github.com/GNOME/gtk/blob/28aa479bf2a2ce3a62ec931f7f175f91f56d3a4b/gtk/a11y/gtkwidgetaccessible.c)
explicitly calls `gtk_window_present_with_time` after focusing the widget.
Changing an injector's device does not prevent the application from requesting
WM activation itself. Replacing generic semantic focus with a click would also
invoke buttons and therefore is not an equivalent fix. This remains a concrete
focus-interference limitation, not a passing isolation case.
