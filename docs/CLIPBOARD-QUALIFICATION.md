# Clipboard interference qualification

`tests/live_clipboard_interference.py` uses real X11 selection owners and an
independent GTK consumer which deliberately requests CLIPBOARD 600 ms after
receiving Ctrl+V. The consumer writes received text to an atomic JSON file;
it has no editable widget and never executes pasted text. The local Ubuntu
24.04 ARM64/Xfwm4 run passed 13 assertions, including real Xfce Clipman
1.6.5 (`2:1.6.5-1build2`).

| Requirement | Local evidence and limits |
| --- | --- |
| CLIP-03 | Initial selection has no owner; delayed multiline Unicode/emoji paste is exact. |
| CLIP-04 | Killing Luda's real xclip owner before the final guard refuses the shortcut. Closing the server after dispatch but before consumption leaves the consumer without text; the earlier response did not claim delivery. |
| CLIP-05, FAULT-08 | A competing real owner before the final guard produces CLIPBOARD_CHANGED and no observed key request. Replacement after the sample can deliver competing bytes and is reported only as dispatched. |
| CLIP-06 | A real competing owner replacing the payload models content rewriting and is detected before dispatch. Actual Clipman with default private settings preserves the exact payload. Arbitrary clipboard-manager transformation plugins are not qualified. |
| CLIP-07 | The owner remains available to a delayed consumer and a second request; a 300,000-byte payload transfers exactly. |
| CONC-10 | Sequential pastes from two independent Desktop controllers can both be consumed as the newer payload by a slow consumer. Neither response claims verified destination text. Simultaneous human ownership changes remain possible. |
| CLIP-01 | PRIMARY sentinel survives ordinary paste and the Clipman case. |

The preflight and post-sample race cases deliberately inject a real xclip
owner change at named Python call boundaries using `patch.object`. This
makes those interleavings reproducible; it does not replace X11 selection
traffic, keyboard input or the GTK destination oracle. No mutation is
retried. The tests cannot prove paste delivery is atomic, and their observed
post-sample interference demonstrates why it is not.

`desktop_paste` reports a sampled clipboard check plus dispatched input.
Use destination text readback or an independent application/file oracle when
exact completion matters. A server restart, owner replacement, confirmation
dialog or slow consumer can invalidate an assumption that dispatch delivered
specific bytes. Do not replay an uncertain paste automatically.

## Run in a private desktop

Install `xfce4-clipman`, GTK3/AT-SPI, Xvfb, Xfwm4, D-Bus and the normal Luda
dependencies during test setup. The suite intentionally fails if Clipman is
missing; it does not silently skip that coverage or install software at run
time. Create a writable `artifacts/clipboard` and run:

```sh
private_dir=$(mktemp -d)
trap 'rm -rf "$private_dir"' EXIT
export XDG_CONFIG_HOME="$private_dir/config"
export XDG_DATA_HOME="$private_dir/data"
export XDG_CACHE_HOME="$private_dir/cache"
xvfb-run -a -s '-screen 0 1440x1000x24 -nolisten tcp' \
  dbus-run-session -- bash -c '
    xfwm4 --compositor=off >/tmp/luda-clipboard-wm.log 2>&1 &
    wm_pid=$!
    trap "kill $wm_pid 2>/dev/null || true" EXIT
    .venv/bin/python tests/live_clipboard_interference.py
  '
```

Private settings must be established before D-Bus starts, including for
Clipman's configuration service. All apps, clipboard owners and fixture
files are owned by the test. Evidence is saved in
`artifacts/clipboard/results.json`; full synthetic received text exists only
in temporary fixtures, which are removed. Run on a fresh display: the first
case intentionally requires an unowned CLIPBOARD. This suite has not yet
been run in hosted CI or across other clipboard managers/toolkits.
