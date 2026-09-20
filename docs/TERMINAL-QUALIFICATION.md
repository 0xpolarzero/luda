# Passive terminal qualification

`tests/live_terminals.py` drives real xterm and xfce4-terminal, each with
bracketed paste enabled and disabled. An owned Python child configures its
PTY in raw mode with ISIG enabled, records exact bytes and counts SIGINT.
It never interprets input or executes pasted text. The local run on Ubuntu
24.04 ARM64 passed all 20 assertions with xterm 390 and xfce4-terminal 1.1.3.

- xterm automatic shortcut selection is refused before changing clipboard
  ownership or PTY contents. The fixture deliberately configures a known
  Ctrl+Shift+V CLIPBOARD binding and tests that explicit override.
- xfce4-terminal automatically selects Ctrl+Shift+V. Plain multiline paste
  presents a native confirmation and sends no bytes before the decision.
  Cancel preserves the empty PTY; a separate paste followed by explicit
  acceptance delivers the expected bytes. The bracketed mode does not show
  this confirmation in the tested configuration.
- Both emulators deliver exact UTF-8 Unicode/emoji, tabs and final line
  breaks, with the terminal's expected LF-to-CR conversion. Bracketed mode
  additionally wraps the bytes in ESC `[200~` and ESC `[201~`. This is an
  exact PTY protocol comparison, not a claim that clipboard LF bytes pass
  through unchanged.
- Ctrl+C produces SIGINT without adding input bytes. xfce4-terminal's
  Ctrl+Shift+C is handled as copy and does not interrupt the child. In the
  tested xterm configuration, Ctrl+Shift+C also produces SIGINT: xterm
  shortcuts depend on bindings, so it is unsafe to assume this means copy.

The copy check uses no selected text and proves the absence of an interrupt;
it does not qualify copying terminal selections or scrollback. Shell command
execution, REPL editing, remote PTYs, tmux/screen, huge pastes and arbitrary
custom terminal bindings remain outside this suite. Paste responses remain
`dispatched`; the independent passive child supplies completion evidence.

## Run and evidence

Use the normal Luda dependencies plus `xterm` and `xfce4-terminal`, installed
during environment setup. Run as an ordinary user with private XDG settings
established before starting a new Xvfb/D-Bus/Xfwm4 session:

```sh
private_dir=$(mktemp -d)
trap 'rm -rf "$private_dir"' EXIT
export XDG_CONFIG_HOME="$private_dir/config"
export XDG_DATA_HOME="$private_dir/data"
export XDG_CACHE_HOME="$private_dir/cache"
xvfb-run -a -s '-screen 0 1440x1000x24 -nolisten tcp' \
  dbus-run-session -- bash -c '
    xfwm4 --compositor=off >/tmp/luda-terminal-wm.log 2>&1 &
    wm_pid=$!
    trap "kill $wm_pid 2>/dev/null || true" EXIT
    .venv/bin/python tests/live_terminals.py
  '
```

Results and synthetic dialog trees are stored under `artifacts/terminals`.
The suite terminates only its own terminals. The native application CI
runner additionally imposes a whole-suite timeout and owned process-group
cleanup. No terminal applications are installed during normal agent use.
