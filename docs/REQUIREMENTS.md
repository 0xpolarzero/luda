# Computer-use acceptance inventory

Frozen inventory for supported Linux computer-use functionality. It is not a promise to implement every optional capability or support every desktop. Removed environment-integration cases retain their original ID gaps. See [validation](VALIDATION.md) for supported behavior and evidence.

## ENV: Linux graphical session attachment (P0)

- **ENV-01** — ARM64 Ubuntu 24.04: install and operate on an existing native X11 desktop.
- **ENV-02** — AMD64 Ubuntu 24.04: same public tool contract and supported workflows.
- **ENV-03** — SSH root account: resolve explicit desktop account and drop privileges before GUI access.
- **ENV-04** — SSH desktop account: attach without root or sudo.
- **ENV-05** — DISPLAY unset in SSH: find the selected desktop session, never assume :0.
- **ENV-06** — Multiple desktop sessions: require an explicit selection instead of choosing the first.
- **ENV-07** — Missing or stale Xauthority: diagnose without exposing cookie contents.
- **ENV-08** — Missing session D-Bus: diagnose and recover through the intended session.
- **ENV-09** — Desktop not started yet: bounded readiness wait and actionable failure.
- **ENV-10** — Desktop restart: reconnect and invalidate every old observation and element handle.

## LIFE: Installation and lifecycle (P0)

- **LIFE-01** — Pinned dependency installation: repeatable artifact hashes and no startup downloads.
- **LIFE-02** — Idempotent install: preserve unrelated desktop and user configuration.
- **LIFE-03** — Upgrade: compatibility check and rollback path for prior release.
- **LIFE-04** — Uninstall: remove owned files and services without deleting user documents.
- **LIFE-05** — Worker crash: release owned resources and expose failure to the client.
- **LIFE-06** — Server restart: reconnect cleanly and reject old handles.
- **LIFE-07** — VM suspend and resume: fresh observation required before mutation.
- **LIFE-08** — VM shutdown during action: report uncertain outcome, never successful completion.
- **LIFE-09** — Read-only or full filesystem: useful startup or artifact error without partial configuration.
- **LIFE-10** — Missing dependency: doctor names the actual missing component and readiness is false.

## MCP: Agent protocol and discovery (P0)

- **MCP-01** — Fresh Codex SSH task: tools and skill discoverable without manual environment instructions.
- **MCP-02** — MCP initialization: supported version negotiated through the SDK.
- **MCP-03** — Tool listing: explicit schemas with bounded arguments and distinct text/key semantics.
- **MCP-04** — Malformed arguments: protocol error before any desktop action.
- **MCP-05** — Tool failure: machine-readable code and MCP isError agree.
- **MCP-06** — Screenshot result: valid image content plus its coordinate metadata in the same response.
- **MCP-07** — Stdout purity: no diagnostic logs corrupt the JSON-RPC stream.
- **MCP-08** — Client disconnect: resources cleaned and outstanding mutation not silently retried.
- **MCP-09** — Transport cancellation: clear outcome and bounded worker cleanup.
- **MCP-10** — Protocol and tool-version changes: versioned migration and backward compatibility policy.

## OBS: Screenshots and observation (P0)

- **OBS-01** — Native screenshot: returned dimensions match the actual root image.
- **OBS-02** — Scaled screenshot: independent horizontal/vertical ratios map to native pixels.
- **OBS-03** — Window capture: client versus frame bounds declared and tested.
- **OBS-04** — Capture during window movement: reject inconsistent observation.
- **OBS-05** — Resolution change after capture: old coordinates rejected.
- **OBS-06** — Expired screenshot: pointer actions rejected before input.
- **OBS-07** — Screenshot from another server: rejected instead of interpreted locally.
- **OBS-08** — Blank or black frame: distinguish real image from failed capture.
- **OBS-09** — Very large desktop: bounded image size and memory use.
- **OBS-10** — Sensitive observation: no automatic screenshot retention or external upload.
- **OBS-11** — Missing glyphs: read-only sampled font diagnostics distinguish rendering gaps from text corruption without claiming universal Unicode coverage or blocking unrelated controls.

## GEO: Coordinates and displays (P0)

- **GEO-01** — Decorated window: frame extents obtained from the window manager, not fixed offsets.
- **GEO-02** — Borderless window: zero extents handled correctly.
- **GEO-03** — Maximized and fullscreen windows: correct origin and bounds.
- **GEO-04** — Window partly off-screen: clip visible region and reject unreachable points.
- **GEO-05** — Negative monitor origin: declared desktop origin and reversible coordinate mapping.
- **GEO-06** — Mixed-DPI monitors: per-monitor mapping or explicit unsupported result.
- **GEO-07** — Fractional scaling: edge points map consistently without cumulative rounding.
- **GEO-08** — Rotated monitor: coordinate transform or explicit unsupported result.
- **GEO-09** — Pointer at right/bottom edge: valid last pixel; exact width/height rejected.
- **GEO-10** — Monitor hotplug: invalidate prior coordinates and report new topology.

## WIN: Window identity and focus (P0)

- **WIN-01** — Duplicate window titles: stable identity rather than title-only targeting.
- **WIN-02** — Several windows in one process: semantic actions scoped to selected top-level.
- **WIN-03** — PID reuse: process start identity invalidates stale handle.
- **WIN-04** — XID reuse in same process: generation or equivalent identity check prevents misdelivery.
- **WIN-05** — Focus stolen before input: reject or report uncertainty; never silently retarget.
- **WIN-06** — Modal child active: inspect/target dialog rather than typing into its blocked parent.
- **WIN-07** — Minimized window: explicit restore/activate with verification.
- **WIN-08** — Window on another workspace: explicit activation and updated observation.
- **WIN-09** — Window closes between lookup and action: bounded stale-target failure.
- **WIN-10** — Human viewer changes focus: no claim that tool serialization excludes human interference.

## WM: Window management (P1)

- **WM-01** — Move window: verify actual accepted location.
- **WM-02** — Resize window: account for app minimum size and size increments.
- **WM-03** — Maximize and restore: preserve prior geometry and report resulting state.
- **WM-04** — Minimize and restore: do not lose window identity.
- **WM-05** — Fullscreen toggle: inspect resulting client/frame layout.
- **WM-06** — Close window: expose unsaved-change dialog and do not assume document saved.
- **WM-07** — Raise window: distinguish raising from gaining keyboard focus.
- **WM-08** — Workspace switch: report active workspace and invalidate old observations.
- **WM-09** — Launch known app: return actual window identity with bounded readiness.
- **WM-10** — Already-running singleton app: associate new request with correct existing/new window.

## AX: Accessibility observation (P0)

- **AX-01** — GTK3 app: real role/name/state/action tree.
- **AX-02** — GTK4 app: version-specific interfaces tested or declared unsupported.
- **AX-03** — Qt app: accessible text and actions validated.
- **AX-04** — Electron app: accessibility activation and tree availability diagnosed.
- **AX-05** — Canvas-only app: report limited semantic coverage and retain screenshot fallback.
- **AX-06** — Large or virtualized tree: bounded traversal, truncation and missing coverage explicit.
- **AX-07** — Hung accessibility provider: subprocess deadline bounds the entire call.
- **AX-08** — Defunct child during traversal: partial result or meaningful failure.
- **AX-09** — Protected field: no secret text returned in ordinary inspection.
- **AX-10** — Ambiguous window mapping: fail rather than expose sibling windows as target descendants.

## SEM: Semantic actions (P0)

- **SEM-01** — Button invocation: exact advertised action name, state observed afterward.
- **SEM-02** — Disabled control: reject action or report application refusal.
- **SEM-03** — Hidden/off-screen control: explicit semantics, no fabricated visibility.
- **SEM-04** — Checkbox and radio: set desired state rather than blind toggle where possible.
- **SEM-05** — Combo box and list selection: identify exact option and verify selection.
- **SEM-06** — Slider and spinbox: respect ranges, steps and locale representation.
- **SEM-07** — Tree expansion: report expanded state and refresh child handles.
- **SEM-08** — Focus element: verify actual focus before subsequent text insertion.
- **SEM-09** — Element path reused with changed role/name: stale handle rejected.
- **SEM-10** — App accepts action but does nothing: dispatched remains distinct from verified.

## TXT: Literal text content (P0)

- **TXT-01** — ASCII multiline LF: exact line breaks preserved.
- **TXT-02** — Trailing newline: not stripped.
- **TXT-03** — Several blank lines: all preserved.
- **TXT-04** — Leading/trailing spaces: no trimming.
- **TXT-05** — Literal tabs: inserted as content, not keyboard navigation.
- **TXT-06** — Non-Latin scripts: exact Japanese, Arabic and Hebrew preserved.
- **TXT-07** — Emoji with modifiers and ZWJ: no code-point loss.
- **TXT-08** — Combining characters: no undocumented Unicode normalization.
- **TXT-09** — Empty replacement: clears editable text; empty insertion is no-op.
- **TXT-10** — Long payload near limit: complete insertion or explicit refusal before partial delivery.
- **TXT-11** — Over-limit payload: reject before touching clipboard or app.
- **TXT-12** — NUL and Escape: explicit unsupported error before mutation.
- **TXT-13** — CRLF/CR: explicit policy, never silent normalization.
- **TXT-14** — Quotes, backticks, dollar signs and backslashes: no shell interpretation.
- **TXT-15** — Bidirectional text: preserve stored string independent of visual order.

## EDIT: Text editing semantics (P0)

- **EDIT-01** — Replacement versus insertion: separate operations and tool descriptions.
- **EDIT-02** — Insertion at caret: preserve surrounding text and selection semantics.
- **EDIT-03** — Selected range: insert replaces only intended selection.
- **EDIT-04** — Read-only field: fail without fallback that mutates another widget.
- **EDIT-05** — Single-line field given multiline: explain rejection or detect app transformation.
- **EDIT-06** — Undo/redo: characterize whether semantic replacement creates an undo step.
- **EDIT-07** — Application formatting/filtering: return mismatch instead of exact-success claim.
- **EDIT-08** — Text entry triggers navigation: no automatic second insertion.
- **EDIT-09** — Caret and selection indices: define code points versus bytes versus grapheme clusters.
- **EDIT-10** — IME composition active: complete/cancel explicitly or refuse conflicting input.

## CLIP: Clipboard ownership and paste (P0)

- **CLIP-01** — CLIPBOARD vs PRIMARY: named selection and application shortcut are explicit.
- **CLIP-02** — Clipboard bytes: verify exact UTF-8 before dispatching paste.
- **CLIP-03** — No prior owner: insertion still works.
- **CLIP-04** — Owner disappears early: report failure without claiming target changed.
- **CLIP-05** — Another app takes ownership before paste: detect or report uncertainty.
- **CLIP-06** — Clipboard manager rewrites content: detect mismatch.
- **CLIP-07** — Slow paste consumer: retain owned data long enough; do not restore prematurely.
- **CLIP-08** — Clipboard restoration: optional explicit policy; never overwrite a newer human copy.
- **CLIP-09** — Rich text/image/file clipboard: negotiate types or explicit unsupported result.
- **CLIP-10** — Terminal Shift+Insert: do not assume it reads CLIPBOARD.

## KEY: Keyboard input (P0)

- **KEY-01** — Return and Tab: intentional key events distinct from literal text.
- **KEY-02** — Modifier chord: correct ordering and release.
- **KEY-03** — Shifted symbols: keyboard layout semantics documented.
- **KEY-04** — Non-US keyboard layout: physical versus logical key behavior tested.
- **KEY-05** — CapsLock and NumLock active: behavior detected or qualified.
- **KEY-06** — Human-held modifier: do not leave modifiers stuck or claim exclusive ownership.
- **KEY-07** — Invalid chord or embedded newline: reject before X11 input.
- **KEY-08** — Key press interrupted: cleanup releases tool-owned keys.
- **KEY-09** — Repeated key with bounded count: no unbounded input flood.
- **KEY-10** — Dead key or compose sequence: defined support or clear unsupported response.

## PTR: Pointer and drag (P0)

- **PTR-01** — Single/double/triple click: timing/count tested in real controls.
- **PTR-02** — Right-click menu: inspect resulting menu before choosing an item.
- **PTR-03** — Hover tooltip: pointer move without accidental click.
- **PTR-04** — Wheel scroll vertical/horizontal: correct target under pointer.
- **PTR-05** — Nested scrolling panes: verify which pane moved.
- **PTR-06** — Smooth scrolling: support or explicit discrete-wheel semantics.
- **PTR-07** — Drag within window: interpolate motion and release button on failure.
- **PTR-08** — Cross-window drag: source/target identities and changed focus handled.
- **PTR-09** — Drag onto file manager: distinguish copy/move/link and confirmation dialog.
- **PTR-10** — Invisible overlay intercepts click: do not equate input dispatch with target activation.

## WAIT: Waiting and synchronization (P0)

- **WAIT-01** — Window appears: condition-based bounded wait.
- **WAIT-02** — Element appears/disappears: fresh tree and explicit timeout.
- **WAIT-03** — Text equals/contains: exact condition with truncation considered.
- **WAIT-04** — Busy UI stops responding: timeout remains bounded.
- **WAIT-05** — Animation after click: settle condition rather than guessed fixed sleep.
- **WAIT-06** — Debounced text update: wait for readback within a defined deadline.
- **WAIT-07** — Long save operation: verify completion rather than button dismissal.
- **WAIT-08** — Clipboard readiness: wait for ownership before input.
- **WAIT-09** — Cancellation while waiting: no further input after cancellation.
- **WAIT-10** — Clock change: use monotonic deadlines.

## ERR: Errors, retries and outcomes (P0)

- **ERR-01** — Precondition failure: effect=none only when no input was sent.
- **ERR-02** — Dispatched input: never labelled verified application success.
- **ERR-03** — Exact readback: state what condition was actually verified.
- **ERR-04** — Mid-action timeout: uncertain outcome, no automatic mutation retry.
- **ERR-05** — Partial compound action: identify completed portion and remaining uncertainty.
- **ERR-06** — Backend exception: structured bounded error without server crash.
- **ERR-07** — Client retries same request: idempotency policy for non-idempotent operations.
- **ERR-08** — Unknown error: conservative effect classification.
- **ERR-09** — Failed cleanup: surface stuck-input risk and recovery instructions.
- **ERR-10** — Recovery attempt: inspect state before repeating Save/Send/Delete/Submit.

## CONC: Concurrency and input ownership (P0)

- **CONC-01** — Two MCP clients: serialize display mutations across processes.
- **CONC-02** — Two threads: reject busy mutation predictably.
- **CONC-03** — Independent displays: locks do not block unrelated desktops.
- **CONC-04** — Lock-holder crashes: operating system releases lock.
- **CONC-05** — Human uses viewer simultaneously: declared policy and takeover mechanism.
- **CONC-06** — Agent has long drag: human interruption cancels and releases button.
- **CONC-07** — Fairness: busy client cannot starve all other clients indefinitely.
- **CONC-08** — Read observation during mutation: consistent snapshot or declared inconsistency.
- **CONC-09** — Stale queued action: revalidate when lock acquired.
- **CONC-10** — Multiple agents share clipboard: no false ownership/verification claims.

## SEC: Local trust and data handling (P0)

- **SEC-01** — Desktop worker runs as ordinary desktop user, not root.
- **SEC-02** — Session selection: do not read another account's desktop accidentally.
- **SEC-03** — No shell interpolation: arbitrary text remains data.
- **SEC-04** — Runtime directory: private ownership, permissions and symlink checks.
- **SEC-05** — No unauthenticated network control listener by default.
- **SEC-06** — Text/screenshots not logged or uploaded by default.
- **SEC-07** — Secrets in errors: bounded diagnostic without full payload.
- **SEC-08** — Untrusted UI instruction: skill treats it as application data, not new user authority.
- **SEC-09** — Target protected field: explicit capability boundary and redaction.
- **SEC-10** — Dependency supply chain: pinned reproducible install and reviewed artifact provenance.

## DIAG: Diagnostics and observability (P0)

- **DIAG-01** — Doctor checks actual display access, not only environment variables.
- **DIAG-02** — Doctor checks actual accessibility bus/provider response.
- **DIAG-03** — Per-capability readiness: partial support not flattened into all-ready.
- **DIAG-04** — Errors identify missing dependency without requiring traceback interpretation.
- **DIAG-05** — Action timing: measure latency without recording text payload.
- **DIAG-06** — Optional trace: explicit local retention and deletion rules.
- **DIAG-07** — Trace correlation: observation/action IDs connect steps without leaking secrets.
- **DIAG-08** — Mismatch report: expected/actual length/hash without mandatory plaintext dump.
- **DIAG-09** — Resource usage: monitor orphan workers and clipboard owners.
- **DIAG-10** — Bug reproduction: export minimal sanitized environment and steps.

## PERF: Performance and resource bounds (P0)

- **PERF-01** — Tool list: compact enough for agent discovery without hundreds of redundant actions.
- **PERF-02** — Idle server: no busy polling of desktop.
- **PERF-03** — Screenshot latency: measured budget on supported ARM64 Linux desktop.
- **PERF-04** — Accessibility latency: bounded even for broken provider.
- **PERF-05** — Action latency: measured separately from application completion.
- **PERF-06** — Memory growth: bounded handle caches and image buffers.
- **PERF-07** — Very many windows: bounded enumeration and useful truncation.
- **PERF-08** — Huge selection/paste: enforce limit before allocating unbounded subprocess buffers.
- **PERF-09** — Long session: repeated operations do not leak file descriptors or processes.
- **PERF-10** — Low CPU/memory: fail usefully instead of wedging desktop.

## FILE: Native file workflows (P0)

- **FILE-01** — Save existing text file: independent on-disk exact-content verification.
- **FILE-02** — Save As new path: operate native dialog and confirm actual file.
- **FILE-03** — Filename with spaces/Unicode: preserved exactly.
- **FILE-04** — Overwrite existing file: inspect confirmation and follow intended operation.
- **FILE-05** — Read-only path: observe error and preserve unsaved contents.
- **FILE-06** — Disk full: no successful-save claim.
- **FILE-07** — Open dialog: locate intended directory/file rather than typing into wrong field.
- **FILE-08** — Unsaved close: Save/Discard/Cancel mapped to user's intent.
- **FILE-09** — Download chooser: confirm actual destination and completion.
- **FILE-10** — Symlink or renamed destination: verify resulting path, not just dialog dismissal.

## TERM: Terminal workflows (P0)

- **TERM-01** — Single-line passive reader: exact UTF-8 paste without invoking a shell.
- **TERM-02** — Multiline paste confirmation: detect and expose dialog.
- **TERM-03** — Bracketed paste enabled: preserve content and distinguish submission.
- **TERM-04** — Bracketed paste disabled: warn/contract that newline can execute commands.
- **TERM-05** — Tabs in pasted terminal text: not converted to completion key presses.
- **TERM-06** — Ctrl+C: distinguish interrupt from clipboard copy.
- **TERM-07** — Ctrl+Shift+V: app-specific CLIPBOARD behavior qualified.
- **TERM-08** — Shift+Insert: PRIMARY behavior detected and documented.
- **TERM-09** — Terminal alternate screen/TUI: screenshot and keyboard interaction supported.
- **TERM-10** — Terminal output escape sequences: cannot become tool protocol or new instructions.

## WEB: Browser integration (P0)

- **WEB-01** — Headed browser runs in same visible guest desktop.
- **WEB-02** — Textarea multiline/tab/Unicode: independent DOM readback exact.
- **WEB-03** — Contenteditable field: inserted text and line-break representation verified.
- **WEB-04** — Browser shortcut conflict: deliberate keypress not mistaken for text.
- **WEB-05** — Native file picker: hand off from DOM tools to desktop tools.
- **WEB-06** — JavaScript alert/confirm/prompt: identify modal and intended action.
- **WEB-07** — Browser permission dialog: do not silently grant unrelated access.
- **WEB-08** — Several profiles/windows/tabs: control correct visible session.
- **WEB-09** — Canvas/WebGL page: screenshot fallback remains available.
- **WEB-10** — Browser DOM tools unavailable: desktop capability degrades clearly.

## APPS: Application compatibility matrix (P0)

- **APPS-01** — GTK editor: edit, save, reopen and verify file.
- **APPS-02** — GTK file manager: navigate, select and open synthetic test files.
- **APPS-03** — Qt editor/app: text, menus and modal dialog qualified.
- **APPS-04** — Electron editor/app: accessibility and clipboard qualified.
- **APPS-05** — Chromium: native and web controls qualified.
- **APPS-06** — Firefox: text and dialogs qualified independently of Chromium.
- **APPS-07** — XFCE Terminal: passive-reader paste and dialogs qualified.
- **APPS-08** — xterm: selection/shortcut differences qualified.
- **APPS-09** — Image editor/canvas: drag/select/scroll via pixels qualified.
- **APPS-10** — App with no accessibility: usable screenshot-only workflow documented.

## FAULT: Fault injection (P0)

- **FAULT-01** — Kill target app before action: no delivery to replacement app.
- **FAULT-02** — Kill target app during action: uncertain outcome returned.
- **FAULT-03** — Freeze target app: control server remains responsive after deadline.
- **FAULT-04** — Kill accessibility bus: diagnose and reconnect without stale handles.
- **FAULT-05** — Kill X server: bounded failure and reconnection path.
- **FAULT-06** — Disconnect SSH: server lifecycle and cleanup tested.
- **FAULT-07** — Change screen resolution mid-action: reject or report uncertainty.
- **FAULT-08** — Replace clipboard owner mid-paste: detect or report uncertainty.
- **FAULT-09** — Fill artifact directory: no global desktop corruption.
- **FAULT-10** — Restart MCP mid-drag: release strategy tested and limitations documented.

## SHIP: Packaging and product acceptance (P0)

- **SHIP-04** — Skill auto-discovery: correct scope and actual tool names.
- **SHIP-05** — Offline startup after install: no vendor login or model API required.
- **SHIP-08** — Version reporting: driver, skill and tool schema identifiable.
- **SHIP-09** — Reproducible acceptance command: independent observer and recorded failures.
- **SHIP-10** — Release gate: no claim of production readiness with unqualified P0 cases.

## WAY: Wayland and alternative backends (P2)

- **WAY-01** — Wayland session: explicitly rejected until a backend is implemented.
- **WAY-02** — Portal permission: no false claim of unattended grant.
- **WAY-03** — Remote-desktop portal: session lifecycle and revocation qualified.
- **WAY-04** — Compositor-specific input: isolated behind same public contract.
- **WAY-05** — XWayland app: do not assume access to native Wayland apps.
- **WAY-06** — Headless compositor: supported startup and capture path documented.
- **WAY-07** — Wayland clipboard: explicit data-control/portal support.
- **WAY-08** — Mixed X11/Wayland: correct capability per target.
- **WAY-09** — Selkies viewer: control engine independent of streaming transport.
- **WAY-10** — Standard VNC-only client: KasmVNC incompatibility identified.

## MEDIA: Optional richer desktop capabilities (P2)

- **MEDIA-01** — Screen recording: explicit start/stop, bounded storage and privacy policy.
- **MEDIA-02** — Audio playback observation: scoped device capture and timestamps.
- **MEDIA-03** — Microphone input: explicit source and lifecycle.
- **MEDIA-04** — Webcam injection: explicit source and user intent.
- **MEDIA-05** — Touch gestures: coordinate and gesture semantics qualified.
- **MEDIA-06** — Stylus pressure: support or explicit unsupported response.
- **MEDIA-07** — OCR: optional local grounding with uncertainty and source coordinates.
- **MEDIA-08** — Image matching: confidence threshold and stale-image handling.
- **MEDIA-09** — Remote file transfer: separate from GUI action with explicit paths.
- **MEDIA-10** — Multi-user sessions: strict session isolation and independent input ownership.

## INTEL: Agent usability and evaluation (P0)

- **INTEL-01** — Agent can infer next action from observation without inspecting driver source.
- **INTEL-02** — Missing accessibility: agent switches to visual mode without invented node IDs.
- **INTEL-03** — Text failure: agent reads back instead of blindly retyping.
- **INTEL-04** — Save timeout: agent checks document/file before retry.
- **INTEL-05** — Stale snapshot: agent reobserves and recomputes coordinates.
- **INTEL-06** — Paste dialog: agent distinguishes blocked workflow from text loss.
- **INTEL-07** — Tool error: concise suggested recovery without hiding uncertainty.
- **INTEL-08** — Token cost: bounded trees and screenshot dimensions evaluated on real tasks.
- **INTEL-09** — Held-out workflows: evaluate apps/tasks not used to develop the driver.
- **INTEL-10** — Repeatability: publish successes, failures, versions and environment, not one lucky demo.

## STATE: State and handle integrity (P0)

- **STATE-01** — Element expires: reject before invoking application.
- **STATE-02** — Server changes: old opaque handles rejected.
- **STATE-03** — Role/name changes at same path: identity revalidated.
- **STATE-04** — Text read limit: truncation explicit; no false full-value comparison.
- **STATE-05** — Window changes title: stable ID preserved when underlying identity unchanged.
- **STATE-06** — Tree restructuring: resolve object identity rather than fragile child index.
- **STATE-07** — Backend loses node: inspect again rather than broad search-and-click fallback.
- **STATE-08** — Observation cache bound: expired entries evicted even in long sessions.
- **STATE-09** — Target window moves after semantic inspect: semantics remain scoped or fail safely.
- **STATE-10** — Action changes modal topology: old action context invalidated or revalidated.

## AUTH: Credentials and authentication UI (P1)

- **AUTH-01** — Password entry: explicitly supported secret-input path without plaintext readback or logs.
- **AUTH-02** — Masked field observation: do not infer hidden contents from placeholder/bullet count.
- **AUTH-03** — Password manager popup: target correct native/browser UI and preserve user intent.
- **AUTH-04** — OTP entry: preserve leading zeros and avoid retaining one-time values.
- **AUTH-05** — Session expiry during workflow: detect login transition rather than act on old coordinates.
- **AUTH-06** — OAuth new window: identify origin/session and resume the intended application.
- **AUTH-07** — Credential field blocks clipboard: explicit alternate supported input or limitation.
- **AUTH-08** — System authentication dialog: distinguish privileged operation from ordinary application input.
- **AUTH-09** — Screen lock: detect locked session and do not claim normal desktop readiness.
- **AUTH-10** — CAPTCHA or human-presence step: expose the requirement instead of claiming automation succeeded.

## MENU: Menus, popups and transient UI (P0)

- **MENU-01** — Application menu bar: open, inspect, choose item and verify effect.
- **MENU-02** — Nested submenu: hover/key navigation with bounded opening wait.
- **MENU-03** — Context menu outside client bounds: explicit transient target instead of guessed parent coordinates.
- **MENU-04** — Unmanaged X11 popup: associate with owner or declare targeting unsupported.
- **MENU-05** — Tooltip overlaps target: avoid interpreting tooltip pixels as the underlying control.
- **MENU-06** — Notification steals attention: preserve intended target and report focus change.
- **MENU-07** — System tray menu: identify actual app/menu rather than panel-wide blind actions.
- **MENU-08** — Tear-off or detached menu: new identity and coordinate context.
- **MENU-09** — Menu disappears on observation: reject stale target and reopen deliberately.
- **MENU-10** — Default button changes in dialog: deliberate action identity rather than blind repeated Return.

## DATA: Forms, tables and virtualized widgets (P1)

- **DATA-01** — Virtualized table rows: scroll and reacquire item identity rather than reuse index.
- **DATA-02** — Sorted/filtered list: act on stable item meaning after order changes.
- **DATA-03** — Multi-selection: explicit replace/add/range semantics and verify selected items.
- **DATA-04** — Editable grid cell: distinguish entering edit mode from replacing whole widget text.
- **DATA-05** — Date/time picker: honor locale, timezone and validation.
- **DATA-06** — Numeric field: detect formatting, rounding and range constraints.
- **DATA-07** — Rich text editor: distinguish plain text content from markup and formatting.
- **DATA-08** — Form validation: observe error rather than mistake submit dispatch for success.
- **DATA-09** — Auto-complete suggestion: select intended suggestion without losing literal input.
- **DATA-10** — RTL layout: visual navigation and text storage semantics remain distinct.

## EVAL: Qualification methodology (P0)

- **EVAL-01** — Independent oracle: verify app/file/DOM state rather than echo driver arguments.
- **EVAL-02** — Repeat runs: disclose run count and intermittent failures.
- **EVAL-03** — Clean guest: reproduce without hidden developer dependencies or prior session state.
- **EVAL-04** — Version matrix: record distro, architecture, desktop, toolkit, browser and driver versions.
- **EVAL-05** — Held-out tasks: include workflows absent from implementation fixtures.
- **EVAL-06** — Negative cases: prove invalid/stale requests do not mutate targets.
- **EVAL-07** — Timeout tests: inspect late effects after recovery, not only elapsed duration.
- **EVAL-08** — Performance measurements: report distributions and environment instead of an unsupported speed claim.
- **EVAL-09** — Evidence retention: synthetic fixtures, failure transcripts and reproducible commands.
- **EVAL-10** — Release decision: separate implementation coverage, local test evidence and production qualification.
