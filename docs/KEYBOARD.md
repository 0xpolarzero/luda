# Named chords and owned-key cleanup

`desktop_press_keys` validates one named chord before resolving the target. It focuses Luda’s private keyboard on the observed window, then checks that device’s focus again immediately before injection. The human keyboard and window-manager active flag are not the agent focus authority. Duplicate modifiers, text strings, lock-toggle keys and unavailable symbols are refused. Semantic typing remains the tool for text.

Punctuation uses X11 symbol names, so zoom shortcuts are `ctrl+plus` and `ctrl+minus`; `ctrl++` is invalid. Supported names are `plus`, `minus`, `equal`, `comma`, `period`, `slash`, `backslash`, `semicolon`, `apostrophe`, `bracketleft`, `bracketright`, `grave`, `asciitilde`, `exclam`, `at`, `numbersign`, `dollar`, `percent`, `asciicircum`, `ampersand`, `asterisk`, `parenleft`, `parenright`, `underscore`, `braceleft`, `braceright`, `bar`, `colon`, `quotedbl`, `less`, `greater`, and `question`. These are symbols, not fixed physical US key positions. Explicit Shift remains a deliberate modifier; `shift+minus` sends that physical chord and can therefore produce underscore. Symbols requiring AltGr or dead-key composition in the current layout remain unsupported.

The isolated planner uses the current XKB keyboard group and mapping. It resolves explicit `ctrl`, `alt`, `shift`, and `super` modifiers and any required Shift for the named symbol. Bare uppercase/lowercase symbols account for Caps Lock without toggling it. For explicit shortcuts, Caps Lock does not silently add a Shift component to a shortcut such as `ctrl+a`. Only symbols available in the current group with ordinary Shift are supported; unavailable mappings return `UNSUPPORTED_KEYMAP` rather than changing the keyboard map, selecting another group, or creating a scratch keycode. Latched input state is refused so sticky/latching state is not consumed unexpectedly.

Before any key event, the planner and injector independently check the agent keyboard’s key state and private XI2 pointer’s button state. Conflicting agent-held keys or buttons return `INPUT_HELD` without clearing or restoring them. The former `xdotool key --clearmodifiers` path is not used: upstream [`xdo_clear_active_modifiers`](https://github.com/jordansissel/xdotool/blob/master/xdo.c) also releases pointer buttons and toggles Caps Lock. Native state/layout definitions follow the [XKB library specification](https://www.x.org/archive/X11R7.7/doc/libX11/XKB/xkblib.html) and installed Xorg protocol headers.

A companion owns the injection subprocess and monitors the controller's pipe. On cancellation, controller death, or its deadline, it kills and waits for that subprocess before releasing only the planned keys that were initially up. A nonce-tagged unmapped resource identifies the injector's X connection. Cleanup verifies that nonce and disconnects any still-live matching injector connection before issuing key releases on the same cleanup connection, preventing its queued requests from following cleanup. Reused/unrelated resources are not disconnected. No release-all-keys command is used. The companion and native helper inherit the selected backend's immutable environment, including after reconnect.

Normal injection releases its pressed keys in reverse order. A completed call reports dispatched input and whether the keyboard group and locks stayed unchanged; it does not prove the application's outcome. A configured keybinding can itself switch layouts or change other application state. The tool never automatically restores those changes or retries input. If the X server is dead or remains stalled, cleanup cannot be guaranteed; the bounded response reports uncertainty rather than claiming success.

All native injector and cleanup connections bind to the session’s private XI2 master pair before state queries or XTest events. Human-held input, including the same keycode, belongs to another device and is not released by agent cleanup. The pair suppresses core event emulation (`send_core=False`) to avoid legacy window-manager focus handling. Legacy core-only applications and custom XKB/accessibility configurations still require compatibility qualification; no shared-device fallback is used. Shared application state can still change while the agent works.

## Qualification

Current [private-device evidence](../tests/evidence/private-input/README.md) verifies real MCP typing, concurrent exact text in separate GTK applications, human-held Shift and mouse preservation, and same-key release isolation. The owner lifecycle probe verifies normal and SIGKILL cleanup. Historical suites described below predate this backend unless their evidence explicitly records the private-device revision; their earlier passes are not new-backend qualification.

`tests/test_keyboard.py` covers grammar before target lookup, held keys and extended buttons, latched state, focus, case and shortcut planning with Caps Lock, current-group refusal, cancellation before subprocess creation, and nonce verification before disconnecting an injector. `tests/live_keyboard_guard.py` starts an owned private Xvfb/XFWM/D-Bus session under the ordinary desktop account and uses an independent XQueryKeymap/XQueryPointer oracle plus GTK key-event/file readback. It tests US upper/lowercase/digits, held Shift and mouse preservation, Caps Lock and Num Lock preservation, French uppercase/shifted digits, exact punctuation text and Control-plus/minus/slash key events in both US and French layouts, and a Russian group that supports Return but refuses unmapped Latin symbols. It kills a controller after an actual Control-down while its injector is deliberately SIGSTOPed, verifies injector death and owned-key release, verifies an unrelated newly held key remains down, and cancels a chord midway.

The native libraries (`libX11`, `libXi`, `libXtst`) and XKB/XInput2/XTest extension availability are checked without injecting input. `desktop_doctor.keyboard` reports availability, current group/locks, held input and latched state; the installer explicitly includes `libxi6` and `libxtst6`.

If the controller's bounded wait ends before the companion proves completion, a separate recovery owner keeps the MCP input gate closed. A stopped owned companion is resumed so it can stop its injector and finish cleanup. Cancellation cleanup for another operation cannot clear that owner. Direct transaction-based Desktop callers also refuse admission during unresolved keyboard recovery. The owner is released only after a valid no-input result, normal completed injection, or verified cleanup. Missing or failed proof leaves input blocked; the implementation does not silently reopen the gate after an arbitrary timeout. Status/control remain available through MCP.

Additional private live fault probes stop both guardian and injector with a key held, verify new input remains blocked after `KEYBOARD_CLEANUP_PENDING`, then permit guardian recovery and independently verify release before reopening the gate. A synthetic guardian selector failure after arming verifies the exception path still consumes ownership metadata and releases the owned keys. Unknown/lost ownership results are conservatively uncertain.

## X server replacement and explicit recovery

All input owners now retain a generation nonce on the original X server's root window. This nonce survives ordinary connections and changes when that root is destroyed by a server restart/reset. Keyboard injection and key cleanup check it on the same native connection that sends events. Mouse press and release use the same generation-bound native pattern, including the parent-death companion. Checking then launching a separate `xdotool` would leave a restart race, so cleanup no longer follows that pattern.

If the original server has been replaced at the same `DISPLAY` and authority path, cleanup returns `session_changed: true` and `cleanup_skipped: true`. It sends no input to the replacement server. This proves that the old session's input ownership has ended; it does not claim that keys/buttons on the replacement session were released. The nonce is lifecycle identity, not a boundary against hostile same-account X11 clients.

`recover_keyboard_input()` provides explicit cleanup recovery for the MCP recovery tool. It retains each interrupted command's original immutable environment. It never retries a chord. It resumes a stopped owned guardian and keeps admission closed while that guardian works. If the same server remains, terminated-injector cleanup can be retried using the saved owned keycodes and injector identity. If generation proof shows a replacement server, the old quarantine owner is discharged without touching the new server's input. A dead/unreachable server, missing ownership metadata, or failed release proof keeps admission closed. Restore or restart the original desktop, request input recovery again, then reconnect/observe as appropriate. Cleanup remains bound to the original private pair and validates its identity before emitting releases. It never substitutes the human devices when that pair has disappeared.

`tests/live_input_generation.py` restarts a private Xvfb at the identical display address and authority path, then holds matching Control and mouse input on the replacement. Both old companions skip cleanup and preserve that input. It also verifies explicit recovery uses the interrupted operation's original environment even when the currently scoped backend points elsewhere, and resolves only on replacement proof without releasing the new input. Private keyboard fixtures isolate XDG configuration, data, cache and runtime before starting their private bus/window manager.

Observed target identity is passed as `send_chord(chord, xid, target_generation=token)`. The planner reads the existing window token on its own X connection; missing or mismatched identity is `STALE_TARGET`. Every plan carries the captured token, including direct low-level calls that omit an expected token. The injector revalidates it and checks token plus private-keyboard focus and device identity under a brief server grab before each key-down, releasing the grab before sleeps. This prevents destruction/reuse between identity validation and a press. Key-up cleanup still runs if the target disappears. Production Desktop callers must supply their observed token rather than silently capturing whatever currently owns the numeric XID.

`tests/live_keyboard_identity.py` destroys and recreates a window using the same XID on the same client connection. Independent XCB KeyPress/KeyRelease events prove old observation and old plan deliver no keys to the replacement, while a fresh token delivers exactly one press/release. The server-restart test additionally reuses the active numeric XID on a new server and refuses the predecessor's observed token.


Named chords accept `count=1` through `20` (default `1`), useful for navigation such as repeated Down. A single owned worker sends complete press/release sequences within the existing operation deadline. Between repetitions it rechecks target identity/focus, held input, mapping, group and locks against the original plan. Any uncertainty stops remaining repetitions; cleanup releases owned keys and never retries the failed chord. Only a successful native completion returns `dispatched_count`; interruption does not invent a partial count. Dispatch counts do not prove an application handled each chord.

Live checks cover 20 exact text characters, repeated line navigation, repeated Shift+A, cancellation after several characters with no later input, exact native event counts for three Return chords and twenty maximum-size five-key chords, and same-process target recreation after the first repetition. The replacement receives no remaining key events.

`tests/live_mcp_keyboard.py` qualifies the public stdio MCP count schema/default, invalid-count rejection without application events, 20-character exact output, line navigation, explicit protocol cancellation midway through a repeat, no later text, and successful subsequent input on the same MCP connection. It owns a private Xvfb/D-Bus/XDG desktop and GTK fixture.

A hosted AMD64 run at `568c9ab` failed the repeated-key cancellation assertion
before the test recorded the returned error details. That artifact alone cannot
establish the exact failing conjunct. Review found a missing fixture precondition:
Clear dispatched input, but the independently published GTK state could still
contain the preceding `AAA`. A length-only threshold could therefore cancel
before new repeat input began. The harness now waits for independently observed
empty text after Clear and requires the new `111` prefix before cancellation.
Failure output includes thread state, error code/effect and synthetic text.
The corrected full private-display keyboard suite passed locally on ARM64; the
original CI failure remains retained (run `35485896308`). This is a test-oracle
correction, not evidence of a production keyboard defect or its repair.

An independent private-GUI probe then reproduced that interleaving by pausing only
the fixture's snapshot publication: public text readback was empty while the
published snapshot remained `AAA`; the old predicate produced CANCELLED/none.
After publication resumed, the empty-baseline/new-prefix predicate produced
CANCELLED/uncertain after real `111`, with no later changes or held keys. This
confirms the race mechanism, not the exact cause of the underspecified CI failure.
All sixteen headless suites subsequently passed on ARM64 at `e987d22` with an
unchanged source fingerprint.

## Interrupted repetitions

A final companion receipt can include `progress`: `unit: "key_chord"`, the requested count, fully acknowledged `dispatched` repetitions, at most one `possibly_partial` repetition, and `not_started` repetitions. These three counts partition the request. `application_outcome_verified` is always false: a complete native press/release acknowledgment does not prove that the application acted on it. Never resume the remainder automatically; observe the application first.

The native worker flushes a start record before possible key input and a completion record only after the chord is released and its keyboard-state check passes. The guardian retains those bounded records internally and drains them after stopping the worker. It does not stream them as an early final response. Missing or malformed proof omits progress; it does not invent zero completed actions. Public errors and sanitized operation history retain only validated numeric counts and fixed labels. A cancelled client need not receive a final reply; `desktop_status` may show the completed cleanup outcome later. If cleanup is still pending and no final receipt exists, progress can remain unavailable.

Validation includes actual private ordinary-account Xvfb exact twenty-repeat text, interrupted repetitions bounded by independent application text, and no held keys or replay; existing controller-death, stopped-guardian and input-recovery checks also pass. Independent real-process protocol probes verify cancellation between acknowledgments, no premature frontend response, and omission on malformed completion records. These are native key-dispatch counts, not rich-editor segment progress or universal compound-action coverage.
