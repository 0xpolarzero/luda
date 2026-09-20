# Real terminal alternate-screen interaction

TERM-09 requires screenshot and keyboard interaction with an alternate-screen
terminal application. `tests/tui_fixture.py` is a real Python curses application
inside xterm, with menu selection, an editable field and explicit confirmation.
It extends the existing passive PTY byte tests with an actual TUI workflow.

`tests/live_tui.py` drives only public stdio MCP tools. The application writes
independent logical state; it does not accept an external command channel to
change selection, text or commit count. The text field consumes printable input
and never executes pasted text. No shell or user terminal is involved.

Run as the ordinary desktop account:

```bash
.venv/bin/python tests/live_tui.py
```

Dependencies are the existing xterm, Xvfb, Xfwm, system Python curses and Luda
runtime. The runner creates private XDG state before its private D-Bus/Xvfb
session, bounds the child to 60 seconds, records source hashes and cleans tagged
processes. Unique output directories under `artifacts/tui/` retain screenshots,
application state, tool observation metadata and runner logs.

## Actual result

First attempt `1789875278692929302` passed four scenarios on source base
`ade1e43`, fingerprint
`69fbf2b4f7d0e8a1e624490a4a51a517c0b07e273a425f216b75a0ef19cafac2`.
Before/after source matched and no tagged processes survived. Environment:
Ubuntu 24.04 ARM64, ordinary UID 1001, XTerm 390, private Xvfb/Xfwm.

1. The application queried xterm's actual private mode 1049 with DECRQM before
   entering curses and while inside it. Responses were reset (`2`) then set
   (`1`), establishing actual alternate-screen entry rather than an app Boolean.
   Public `desktop_observe` returned and retained an image of the curses UI.
2. Down selected Beta; Tab focused the field. Explicit `ctrl_shift_v` pasted
   `café $(never-execute)` through the configured xterm clipboard binding.
   Independent state confirmed literal text and zero commits. Tab then Return
   committed precisely item index 1 and that text, with commit count exactly one.
3. Escape ended curses. A second mode query reported reset (`2`); xterm remained
   alive and the same Luda window generation was still enumerated. A public
   screenshot showed the original pre-curses terminal content and restored
   passive session message.
4. An explicit `q` sent through public keyboard input reached the restored
   session and cleanly finished its passive reader.

The confirmed TUI and restored terminal screenshots were visually reviewed.
The reusable test checks image availability, actual terminal mode replies and
application effects; it is not an autonomous screenshot interpretation test.
The screen instructions and field/menu state are rendered by curses itself.
The fixture does not emulate the TUI by drawing a synthetic screenshot.

## Limits

This is one small curses application and xterm version, not every full-screen
terminal program, emulator, nested multiplexer, resize/signal recovery path,
mouse reporting mode, complex grapheme layout or remote SSH terminal. The original
session is an owned passive Python reader, not a user's shell. No semantic tree
for terminal contents is assumed. Explicit terminal paste binding is part of the
fixture setup; it does not establish that xterm's automatic shortcut selection is
supported. See [terminal byte/clipboard evidence](TERMINAL-QUALIFICATION.md) for
those separate behaviors.

No driver defect or runtime change was indicated. This is local TERM-09 evidence;
release qualification remains unchanged and no current matrix pass is inferred
from this standalone result.

The optional `tui` qualification-matrix registration runs this same private-session
launcher. Registration adds no pass or qualification claim.
