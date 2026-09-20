# Catalog gap audit

This audit reviews the current source and test inventory, not just test totals. The catalog has 346 cases: 296 P0, 30 P1 and 20 P2. Every case remains release-unqualified until its acceptance criterion has sufficient evidence. A unit mapping is not production qualification.

`test-map.json` now maps 118 requirements to 186 distinct existing unit methods. Some requirements share tests because one narrow assertion informs several criteria. The map explicitly states those limits. Live suites additionally exercise application effects, but their results must be associated with the exact source/environment that ran them; historical artifact files must not be imported as current passes.

## Confirmed runtime gaps at the audited snapshot

These require implementation or an explicit supported-scope decision; a fresh Mac test alone cannot resolve them. Active development may close an item after this snapshot.

| Cases | Gap | Existing behavior |
|---|---|---|
| ENV-09 | Bounded wait for a desktop session starting up | Session discovery currently fails immediately when no matching session exists. |
| LIFE-07 | Suspend/resume invalidation | Screenshot/element expiration uses monotonic elapsed time; no suspend-generation check forces fresh observations. |
| WM-05, WM-07 | Fullscreen and raise without focus | Window API offers move/resize/maximize/minimize/restore/close/workspace, not these distinct operations. |
| WAIT-02 | Wait for an element to appear/disappear | Current conditions cover windows and text in an existing handle; no fresh-tree element predicate. |
| WAIT-05 | Explicit UI-settled predicate | No pixel/semantic-stability condition. Text/window conditions can handle some workflows, but not arbitrary animation completion. |
| EDIT-10 | IME composition handling | No composition-state detection or explicit complete/cancel/refuse path. |
| KEY-08, FAULT-10 | Top-level process death during held keyboard input | Graceful cancellation/drag cleanup is tested; unconditional keyboard release after abrupt server death is not established. |
| AUTH-09 | Screen-lock awareness in readiness | A working X11 display and accessibility bus can still belong to a locked desktop; doctor does not identify that distinction. |
| CONC-07 | Fairness under competing clients | A nonblocking lock returns BUSY; no fairness guarantee or queued ownership protocol. |
| OBS-09 | Explicit native screenshot memory/pixel budget | Returned image width is bounded, but the initial native screenshot/decoded pixel allocation has no explicit product budget. |
| PERF-07 | Useful truncation for very many windows | Batching/deadlines bound some work, but complete enumeration has no visible count/truncation contract. |

Two more confirmed source-level resource concerns deserve specific tests: subprocess `communicate()` captures unbounded output before parsing, and backend timeout alone does not establish bounded memory use. These are implementation concerns, separate from CPU/memory stress qualification in PERF-10.

## Changes after the audit

The rows above describe the audited snapshot. Subsequent implementation added bounded session readiness (`c0f117f`), suspend-aware expiry/invalidation (`d2cb486`, `6c4630f`, `d2685bb`), fullscreen and verified raise (`50b847b`), fresh-element and sampled-pixel waits (`336226b`, `00d927c`), screenshot pixel bounds (`5514140`), and bounded subprocess output (`2e8a1b3`, `035c792`). Doctor now reports read-only screensaver/login1 hints (`e275dbc`), without claiming unknown means unlocked. A held-mouse companion survives controller death (`bc82396`, `0868298`); this does not establish all keyboard-crash or concurrent-human-input guarantees.

Authoritative Chromium document selections fix the astral-offset discrepancy (`34b5a59`); the rich-text representation gap remains explicit (`4780dce`). Subsequent work also added filtered/paginated batched window discovery, validated live session reconnect, cooperative FIFO admission, installable Codex plugin packaging, strict pre-coercion MCP validation, pinned build dependencies, install integrity checks, and real storage-fault handling. Native file-manager/editor/terminal suites now run in hosted AMD64 CI. Independent fresh-agent form, save, screenshot, recovery and adversarial-document tasks have passed; see their detailed records.

The historical gaps below must be read alongside [current validation](VALIDATION.md). Clipboard interference, native file decisions and session replacement now have targeted real evidence, while broader matrices remain incomplete. IME probes confirmed a generic-backend limitation rather than closing it. Neither these implementations nor their narrow regression tests automatically qualify the associated catalog cases.

Further work added native XKB planning and owned keyboard/click/drag injectors,
explicit MCP cleanup recovery, atomic injector identity/disconnect, and RandR
topology invalidation. Real controller death, stopped workers, same-address server
replacement and logical-monitor changes have independent live oracles. Firefox
now has provider-specific Unicode normalization and exact selection insertion;
Electron's older Chromium selection limitation remains refused. Changed-length
provider reads can no longer verify an old bounded prefix as the complete value.
See [keyboard](KEYBOARD.md), [pointer](POINTER-INPUT.md),
[recovery](MCP-INPUT-RECOVERY-QUALIFICATION.md), [topology](DISPLAY-TOPOLOGY.md),
[Firefox](FIREFOX-QUALIFICATION.md) and [provider review](PROVIDER-TEXT-REVIEW.md).

## Provider discrepancies found by live tests

| Cases | Current discrepancy | Evidence |
|---|---|---|
| EDIT-03, EDIT-09, WEB-02 | Chromium astral selection reads the wrong ending offset in a later accessibility request, while the DOM mutation replaces the intended emoji sequence | `live_browser.py` logs full synthetic before/after text, selection and DOM oracle. |
| WEB-03, DATA-07 | Multiline contenteditable exposes hypertext/embedded-object representation instead of the DOM plain-text string expected by the fallback | The DOM receives exact text, but backend exact-readback verification rejects it. |

These are not passed merely because a clipboard path changes the DOM correctly. They require correct provider interpretation or an honest pre-input unsupported boundary. The browser suite returns failure until the semantic assertions pass.

## Local qualification gaps

These are mostly broader evidence requirements, not proof that another specialized runtime tool is needed:

- **Display matrix:** GEO-02 through GEO-08 and real GEO-10; borderless/fullscreen, partially offscreen windows, multiple/negative-origin monitors, fractional/mixed scaling, rotation and hotplug.
- **Keyboard/IME matrix:** KEY-03 through KEY-06, KEY-09/10 and EDIT-10; layouts, lock keys, human-held modifiers, repeat behavior, dead keys and composition.
- **Clipboard interference:** CLIP-03 through CLIP-07, CONC-10 and FAULT-08; real owner replacement, clipboard managers, slow consumers and competing processes. Byte matching at one instant is not continued-ownership proof.
- **File failures:** FILE-04 through FILE-06 and FILE-08 through FILE-10; overwrite, readonly/full disk, unsaved-close choices, download completion and renamed/symlink destinations. Existing Save/Save As and upload tests do not cover all these.
- **Application matrix:** APPS-02/04/06/08/09/10; complete file-manager, Electron, Firefox, xterm, image-editor and screenshot-only workflows. GTK/Qt fixtures and Chromium do not substitute for these.
- **Fault/lifecycle matrix:** LIFE-06 through LIFE-09, MCP-08, FAULT-04/06/08/09/10; real disconnect, bus restart, filesystem exhaustion, top-level crash and late effects after recovery.
- **Complex controls/authentication:** DATA-01/02/04/05/07/08/09/10 and AUTH-03 through AUTH-10; virtualized grids, sorting, validation, locale, rich text, manager popups, OTP/OAuth, system authorization and human-presence steps. Generic controls may support workflows, but coverage is not demonstrated.
- **Menus:** MENU-02/05/06/07/08/10; nested menus, tooltips/notifications, tray and detached menus, changing default buttons. A context-menu fixture covers only part of this surface.
- **Long-running quality and usability:** PERF-03/05/06/09/10, INTEL-01 through INTEL-10 and EVAL-02/05/08; latency distributions, hours-long resource behavior, repeated and held-out autonomous-agent tasks. A human-written test script cannot establish intuitive agent use by itself.

Several catalog criteria explicitly permit an unsupported result or a stated limitation, for example mixed-DPI/rotated displays, rich clipboard and dead-key input. Do not silently reinterpret these as either implemented full functionality or mandatory new backends. Record the actual supported boundary and test that refusal.

## External environment qualification

The following need environments outside this Linux-only checkout or product integration, rather than another guest-side unit test:

- ENV-01/02 and EVAL-03: clean microsandbox ARM64/AMD64 guests. Hosted AMD64 CI is useful but is not microsandbox qualification.
- MCP-01, SHIP-01/02/03/04: actual Silo provisioning and a fresh Mac Codex SSH connection discovering the tools and skill automatically. Generated configuration files demonstrate correct structure, not host-side discovery.
- SHIP-06/07: Silo's guest health UI and human viewer reconnecting to the same session.

No user confirmation is required merely to continue implementation or local tests. These entries explain why local passing tests cannot justify a claim that the complete external product experience has already been validated.

## Release interpretation

Keep the catalog priorities unchanged unless the user explicitly changes scope. Do not delete hard cases, downgrade P0 entries to make a score look complete, or convert missing evidence into a pass. Report separately: implemented capability, local verified behavior, provider limitations, untested matrices and external onboarding evidence. The qualification runner enforces that passing unit tests alone never produce `qualified`.
