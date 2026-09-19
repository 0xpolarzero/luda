# Implementation and validation status

Date: 2026-09-19. Environment: actual Silo ARM64 Ubuntu 24.04 guest, XFCE/X11 on `:1`, KasmVNC 1.5.0, 1440×900. Tests run as `silo-desktop`, not root. This is local evidence for a prototype, not certification of the whole requirements catalog.

## Implemented versus qualified

| Capability | Implementation | Evidence and limits |
|---|---|---|
| Guest session attachment | Explicit account/session launcher, privilege drop | Worked from SSH/root into current desktop and from desktop account. Fresh VM/Mac onboarding untested. |
| MCP | Official pinned SDK, 14 typed tools, images and errors | Real stdio initialize/list/call tests pass. Disconnect/cancellation/version matrix incomplete. |
| Desktop observation | Screenshots, scaling metadata, client/frame geometry, window identities | Native screenshot dimension and scaled-click checks pass. Multimonitor/fractional/Wayland unqualified. |
| Semantic inspection | Window-scoped AT-SPI subprocess with deadline | GTK fixture, Mousepad dialog and XFCE Terminal dialog exercised. Qt/Electron/GTK4 unqualified. |
| Text replacement | EditableText plus exact readback | Unicode, combining marks, emoji, LF, tabs, empty string, whitespace and 8,005-character payload tested. Application transformation and undo need more coverage. |
| Text insertion | Managed CLIPBOARD + explicit app shortcut | Exact independent readback in GTK, Chromium and passive terminal fixture. Tool response intentionally says dispatched; universal destination verification not implemented. |
| Pointer/key actions | Click, wheel, same-window drag, bounded key chords | Scaled button click and save shortcuts tested. Drag/scroll timing and cross-app behavior unqualified. |
| Semantic actions/focus | Advertised action, role/name/path revalidation, enabled/showing check | Button, text focus, native Save As and terminal paste dialog exercised. Complex widgets/menu coverage incomplete. |
| Stale target prevention | Expiring IDs, process identity, geometry/focus checks | Expired screenshot/element, moved/closed window and invalid coordinates rejected. Same-process XID reuse and unmanaged overlay interception remain limitations. |
| Bounded failures | Deadlines and cross-server lock | Frozen app refused in about one second; inspection recovered after resume. Hard timeout unit test confirms uncertain-effect classification. |
| Packaging | Wheel, source distribution, runtime hash lock, skill | Isolated wheel install and desktop doctor smoke check. System provisioning script syntax checked; full clean-VM apt installation untested. |

## Test suites

| Suite | Assertions | Result | Evidence |
|---|---:|---|---|
| Pure contracts | 8 tests | Passed | `tests/test_contracts.py`; local unittest output |
| Native desktop integration | 31 checks | Passed | `artifacts/native/results.json` |
| Actual MCP protocol | 8 checks | Passed | `artifacts/mcp/results.json`, tool schemas and screenshot |
| Real applications | 7 checks | Passed | `artifacts/apps/results.json`, saved files and dialog trees |

54 tests/checks across these suites, including 46 live checks. Several checks cover variants of the same capability; this is not 54 independently qualified product features or a general reliability percentage. The packaged doctor smoke check is additional. The broader catalog's `qualification=unqualified` means release-level evidence is still incomplete, even where local probes pass.

### Exact real-application outcomes

- Mousepad saved the requested Unicode multiline text to an existing file, with independent file readback.
- Mousepad's native Save As dialog created a second filename containing spaces and Japanese characters; file contents matched exactly.
- Headed Chromium accepted ASCII multiline, literal Tab, Unicode/emoji/combining marks and trailing newlines through this driver's clipboard input. Playwright created the offline page and independently read its textarea; it did not supply the candidate's paste.
- XFCE Terminal displayed its multiline-paste confirmation. The driver observed its accessible Paste button and invoked that action. A passive Python reader, not a shell, then recorded the exact payload including tabs and newlines. This is proof for that terminal configuration, not proof for xterm or every terminal mode.

### Negative and recovery checks

- NUL, CRLF, invalid surrogate text, oversized input and malformed key chords were refused.
- Hidden editable controls and disabled buttons were refused before mutation.
- Protected text reads were refused.
- Out-of-image coordinates, expired screenshot IDs, window movement and expired element IDs were refused.
- A competing server instance received BUSY for the same display lock.
- A stopped fixture application produced a bounded refusal; after SIGCONT, inspection worked again.
- Closed window identity was rejected.
- Runtime symlinks/insecure permissions were rejected; shell metacharacters remained data in subprocess arguments.

## Failures found while developing

1. GTK reported decorated accessibility-frame bounds while Xlib reported client bounds. Initial exact matching failed. Fixed by consulting actual `_NET_FRAME_EXTENTS` and matching either legitimate rectangle, with ambiguity rejected.
2. GI's Accessible/Text naming collision made a generic `get_text(start,end)` call invalid. Fixed by calling the actual `Atspi.Text` interface explicitly.
3. An early Save As test selected a hidden editable control in the dialog. The first attempt failed. Fixed the harness to select the visible control and tightened the driver to reject hidden/disabled mutation. The corrected Save As workflow passed. GTK/ATK diagnostic warnings still appeared during dialog traversal; the source of those warnings is not resolved and the successful file oracle does not make them disappear.
4. The independent fixture originally rewrote JSON in place. A read caught the transient empty file. Changed the fixture to atomic replace; this was an oracle race, not evidence of lost application text.
5. The frozen-app test initially assumed every attempted mutation must be uncertain. In this case lookup failed before mutation, so effect=none was appropriate. The test now checks bounded refusal and recovery; hard subprocess-timeout semantics have a separate test.

These are recorded because the custom implementation needs the same scrutiny applied to upstream tools. Passing after a correction does not establish broad application compatibility.

## Release blockers

1. **Input reliability:** application-aware verified insertion, IME/keyboard-layout behavior, clipboard interference, explicit credential input and appropriate app-specific paths. Current clipboard insertion is a documented primitive.
2. **Identity and coordination:** same-process XID/node reuse, popups/overlays, human takeover and the race between validation and event delivery.
3. **Lifecycle:** cancellation, client disconnect, X-server/accessibility-bus restart, stale queued actions, request deduplication and cleanup under process death.
4. **Missing interaction surface:** condition-based waits, window management, cross-window drag, complex selection widgets and native transient-menu targeting.
5. **Qualification breadth:** clean ARM64/AMD64 guests, Qt/Electron/GTK4/Firefox/xterm, file manager/canvas apps, multiple display configurations, repeat and held-out workflows.
6. **Product integration:** clean installation/upgrade/rollback, Silo packaging, actual fresh Mac Codex SSH discovery of both tools and skill. No global Codex registration or Silo source change has been made.

Optional Wayland, OCR, video/audio and rich clipboard features are cataloged separately. The existing KasmVNC desktop remains appropriate for this prototype; replacing it is not a prerequisite for these improvements.
