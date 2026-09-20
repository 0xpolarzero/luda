# Implementation and validation status

The project is under active development. Local evidence comes from an ARM64 Ubuntu 24.04 Silo guest with XFCE/X11, KasmVNC 1.5.0 and a 1440×900 display, plus isolated Xvfb/XFWM4 sessions. Shared-desktop tests attach as the ordinary desktop account. GitHub CI independently runs unit and fresh X11 workflows on Ubuntu AMD64.

The [345-case catalog](REQUIREMENTS.md) is an acceptance target, not a claim that every feature exists or passes. [Qualification records](QUALIFICATION.md) bind evidence to source and environment; passing a local fixture does not automatically change release qualification.

## Implemented capabilities and evidence

| Capability | Independent evidence | Remaining limits |
|---|---|---|
| Session attachment | Root-to-desktop privilege drop, existing SSH session attachment, installed doctor | Fresh Mac SSH onboarding and fresh microsandbox provisioning untested |
| MCP lifecycle | Actual stdio initialize/list/call/image/error, explicit cancellation, responsive status, peer pause | Client timeout may not cancel; cancellation acknowledgment may precede cleanup |
| Target identity | Window generation token survives remap; actual same-process same-XID destruction/reuse changes it | Identical semantic widget path/name/role reuse remains possible |
| Screenshots and pointer | Scaled coordinates, moved/expired/resized targets; real nested menus; covering popup refusal | Content can change between checks and input; multimonitor configurations unqualified |
| Text editing | GTK3 independent widget readback, Qt UTF-16 boundary conversion, protected synthetic-value hash oracle | Browser hypertext/selection compatibility still being corrected; GTK4 provider defects recorded |
| Clipboard | Exact multiline Unicode/tab input in GTK, Chromium and passive terminal; confirmation dialog observed | CLIPBOARD ownership check is sampled; raw paste does not verify destination |
| Semantic controls | GTK3/Qt lists and radios, desired checkbox/value/expansion, GTK committed combo choice | Qt combo without semantic commit action refused; custom widgets unqualified |
| Interaction | Window/workspace state, cross-window GTK drag with independent UTF-8 transfer, nested menu callback | Broader drag/scroll/key-layout/IME application matrix incomplete |
| Application launching | Gio desktop entries, exact Unicode argv, detached GTK launches, input validation | D-Bus/singleton and terminal routing qualification ongoing |
| Isolation and recovery | Frozen provider timeout/recovery, X-server helper death/restart, process-group timeout cleanup | Escaped process sessions cannot be treated as killed; full session-bus rediscovery incomplete |
| Installation | Real immutable release install, doctor, repeat install, rollback/uninstall logic and adversarial tests | System provisioning and Mac/Silo registration require external integration runs |

## Reproducible suites

- `tests/test_*.py`: argument, identity, selection, cancellation, process cleanup, installer and evidence contracts. Use unittest discovery for the current test count.
- `scripts/headless_tests.py`: native desktop, actual MCP, cancellation and shared pause on a fresh X11 desktop. The latest local run passed all four suites after menu/occlusion integration.
- `tests/live_semantic.py`, `live_toolkits.py`, `live_controls.py`, `live_combo.py`: provider behavior with independent GTK3/GTK4/Qt widget oracles. See [toolkit details](TOOLKIT-QUALIFICATION.md) and [protected/option controls](PROTECTED-AND-OPTION-CONTROLS.md).
- `tests/live_browser.py`: offline Chromium forms, Unicode selection, dialogs, native file upload, focus theft, rejected/transformed/delayed paste. Failures remain explicit. See [browser evidence](BROWSER-QUALIFICATION.md).
- `tests/live_apps.py`: Mousepad save/Save As with exact file readback, Chromium clipboard forms, XFCE Terminal multiline-paste confirmation and passive-reader bytes.
- `tests/live_menu.py`, `live_drag.py`, `live_interaction.py`, `live_window_tokens.py`, `live_x11_isolation.py`: actual menus, transfer, window states, XID reuse and X-server recovery.
- `tests/live_application_launch.py`: private desktop-entry registry and owned launched applications; no modification of the real user registry.

Tests save synthetic evidence under ignored `artifacts/`. A changed source revision requires new evidence for affected behavior. Avoid comparing raw assertion counts as a reliability percentage.

## Bugs the tests have exposed

- GTK decorated-frame geometry differed from X11 client geometry; matching now uses actual frame extents.
- Qt text uses UTF-16 offsets and insertion length; passing UTF-8 byte lengths inserted NUL padding. Independent widget readback caught it; conversions now happen at the provider boundary.
- GTK4 reports unavailable screen coordinates and has selection/caret provider failures; ambiguous windows and unverifiable changes are refused.
- Chromium exposes editable Text without EditableText. The driver now has an accessibility-guided clipboard fallback, but Unicode selection/hypertext readback still requires correction.
- A chooser disappearing after Return was cancellation, not successful upload. The browser test now verifies the selected filename and file contents independently.
- A highlighted combo option was not a committed combo value. The GTK path now activates and verifies the enclosing combo selection.
- A timeout in Python subprocess communication could lose pending large stdin. Worker input now uses a private file, with regression coverage.
- Cancellation acknowledgment can arrive before cleanup. Tests wait for operation status and independently check that no late input arrives.

## Release work still required

Complete provider compatibility and supported application workflows; broaden keyboard-layout/IME, clipboard interference and display configuration tests; qualify accessibility-bus/session replacement; address stale semantic object reuse and duplicate requests where feasible; exercise independent held-out tasks and repeated runs; and test clean ARM64/AMD64 Silo provisioning plus actual Mac Codex SSH discovery.

Wayland, OCR, audiovisual interaction and rich clipboard formats remain separate catalog expansions. The existing XFCE/KasmVNC GUI is the current backend; these tool improvements do not require replacing it.
