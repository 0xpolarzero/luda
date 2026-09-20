"""Canonical acceptance catalog. Cases start unqualified; passing one probe is not certification."""
import json
from pathlib import Path

# P0 = required for supported release; P1 = full-product capability; P2 = optional expansion.
GROUPS = [
('ENV','Guest and session attachment','P0','''ARM64 Ubuntu 24.04 fresh VM: install and operate without nested virtualization
AMD64 Ubuntu 24.04 fresh VM: same public tool contract and acceptance workflows
SSH root account: resolve explicit desktop account and drop privileges before GUI access
SSH desktop account: attach without root or sudo
DISPLAY unset in SSH: find the selected desktop session, never assume :0
Multiple desktop sessions: require an explicit selection instead of choosing the first
Missing or stale Xauthority: diagnose without exposing cookie contents
Missing session D-Bus: diagnose and recover through the intended session
Desktop not started yet: bounded readiness wait and actionable failure
Desktop restart: reconnect and invalidate every old observation and element handle'''),
('LIFE','Installation and lifecycle','P0','''Pinned dependency installation: repeatable artifact hashes and no startup downloads
Idempotent install: preserve unrelated desktop and user configuration
Upgrade: compatibility check and rollback path for prior release
Uninstall: remove owned files and services without deleting user documents
Worker crash: release owned resources and expose failure to the client
Server restart: reconnect cleanly and reject old handles
VM suspend and resume: fresh observation required before mutation
VM shutdown during action: report uncertain outcome, never successful completion
Read-only or full filesystem: useful startup or artifact error without partial configuration
Missing dependency: doctor names the actual missing component and readiness is false'''),
('MCP','Agent protocol and discovery','P0','''Fresh Codex SSH task: tools and skill discoverable without manual environment instructions
MCP initialization: supported version negotiated through the SDK
Tool listing: explicit schemas with bounded arguments and distinct text/key semantics
Malformed arguments: protocol error before any desktop action
Tool failure: machine-readable code and MCP isError agree
Screenshot result: valid image content plus its coordinate metadata in the same response
Stdout purity: no diagnostic logs corrupt the JSON-RPC stream
Client disconnect: resources cleaned and outstanding mutation not silently retried
Transport cancellation: clear outcome and bounded worker cleanup
Protocol and tool-version changes: versioned migration and backward compatibility policy'''),
('OBS','Screenshots and observation','P0','''Native screenshot: returned dimensions match the actual root image
Scaled screenshot: independent horizontal/vertical ratios map to native pixels
Window capture: client versus frame bounds declared and tested
Capture during window movement: reject inconsistent observation
Resolution change after capture: old coordinates rejected
Expired screenshot: pointer actions rejected before input
Screenshot from another server: rejected instead of interpreted locally
Blank or black frame: distinguish real image from failed capture
Very large desktop: bounded image size and memory use
Sensitive observation: no automatic screenshot retention or external upload
Missing glyphs: read-only sampled font diagnostics distinguish rendering gaps from text corruption without claiming universal Unicode coverage or blocking unrelated controls'''),
('GEO','Coordinates and displays','P0','''Decorated window: frame extents obtained from the window manager, not fixed offsets
Borderless window: zero extents handled correctly
Maximized and fullscreen windows: correct origin and bounds
Window partly off-screen: clip visible region and reject unreachable points
Negative monitor origin: declared desktop origin and reversible coordinate mapping
Mixed-DPI monitors: per-monitor mapping or explicit unsupported result
Fractional scaling: edge points map consistently without cumulative rounding
Rotated monitor: coordinate transform or explicit unsupported result
Pointer at right/bottom edge: valid last pixel; exact width/height rejected
Monitor hotplug: invalidate prior coordinates and report new topology'''),
('WIN','Window identity and focus','P0','''Duplicate window titles: stable identity rather than title-only targeting
Several windows in one process: semantic actions scoped to selected top-level
PID reuse: process start identity invalidates stale handle
XID reuse in same process: generation or equivalent identity check prevents misdelivery
Focus stolen before input: reject or report uncertainty; never silently retarget
Modal child active: inspect/target dialog rather than typing into its blocked parent
Minimized window: explicit restore/activate with verification
Window on another workspace: explicit activation and updated observation
Window closes between lookup and action: bounded stale-target failure
Human viewer changes focus: no claim that tool serialization excludes human interference'''),
('WM','Window management','P1','''Move window: verify actual accepted location
Resize window: account for app minimum size and size increments
Maximize and restore: preserve prior geometry and report resulting state
Minimize and restore: do not lose window identity
Fullscreen toggle: inspect resulting client/frame layout
Close window: expose unsaved-change dialog and do not assume document saved
Raise window: distinguish raising from gaining keyboard focus
Workspace switch: report active workspace and invalidate old observations
Launch known app: return actual window identity with bounded readiness
Already-running singleton app: associate new request with correct existing/new window'''),
('AX','Accessibility observation','P0','''GTK3 app: real role/name/state/action tree
GTK4 app: version-specific interfaces tested or declared unsupported
Qt app: accessible text and actions validated
Electron app: accessibility activation and tree availability diagnosed
Canvas-only app: report limited semantic coverage and retain screenshot fallback
Large or virtualized tree: bounded traversal, truncation and missing coverage explicit
Hung accessibility provider: subprocess deadline bounds the entire call
Defunct child during traversal: partial result or meaningful failure
Protected field: no secret text returned in ordinary inspection
Ambiguous window mapping: fail rather than expose sibling windows as target descendants'''),
('SEM','Semantic actions','P0','''Button invocation: exact advertised action name, state observed afterward
Disabled control: reject action or report application refusal
Hidden/off-screen control: explicit semantics, no fabricated visibility
Checkbox and radio: set desired state rather than blind toggle where possible
Combo box and list selection: identify exact option and verify selection
Slider and spinbox: respect ranges, steps and locale representation
Tree expansion: report expanded state and refresh child handles
Focus element: verify actual focus before subsequent text insertion
Element path reused with changed role/name: stale handle rejected
App accepts action but does nothing: dispatched remains distinct from verified'''),
('TXT','Literal text content','P0','''ASCII multiline LF: exact line breaks preserved
Trailing newline: not stripped
Several blank lines: all preserved
Leading/trailing spaces: no trimming
Literal tabs: inserted as content, not keyboard navigation
Non-Latin scripts: exact Japanese, Arabic and Hebrew preserved
Emoji with modifiers and ZWJ: no code-point loss
Combining characters: no undocumented Unicode normalization
Empty replacement: clears editable text; empty insertion is no-op
Long payload near limit: complete insertion or explicit refusal before partial delivery
Over-limit payload: reject before touching clipboard or app
NUL and Escape: explicit unsupported error before mutation
CRLF/CR: explicit policy, never silent normalization
Quotes, backticks, dollar signs and backslashes: no shell interpretation
Bidirectional text: preserve stored string independent of visual order'''),
('EDIT','Text editing semantics','P0','''Replacement versus insertion: separate operations and tool descriptions
Insertion at caret: preserve surrounding text and selection semantics
Selected range: insert replaces only intended selection
Read-only field: fail without fallback that mutates another widget
Single-line field given multiline: explain rejection or detect app transformation
Undo/redo: characterize whether semantic replacement creates an undo step
Application formatting/filtering: return mismatch instead of exact-success claim
Text entry triggers navigation: no automatic second insertion
Caret and selection indices: define code points versus bytes versus grapheme clusters
IME composition active: complete/cancel explicitly or refuse conflicting input'''),
('CLIP','Clipboard ownership and paste','P0','''CLIPBOARD vs PRIMARY: named selection and application shortcut are explicit
Clipboard bytes: verify exact UTF-8 before dispatching paste
No prior owner: insertion still works
Owner disappears early: report failure without claiming target changed
Another app takes ownership before paste: detect or report uncertainty
Clipboard manager rewrites content: detect mismatch
Slow paste consumer: retain owned data long enough; do not restore prematurely
Clipboard restoration: optional explicit policy; never overwrite a newer human copy
Rich text/image/file clipboard: negotiate types or explicit unsupported result
Terminal Shift+Insert: do not assume it reads CLIPBOARD'''),
('KEY','Keyboard input','P0','''Return and Tab: intentional key events distinct from literal text
Modifier chord: correct ordering and release
Shifted symbols: keyboard layout semantics documented
Non-US keyboard layout: physical versus logical key behavior tested
CapsLock and NumLock active: behavior detected or qualified
Human-held modifier: do not leave modifiers stuck or claim exclusive ownership
Invalid chord or embedded newline: reject before X11 input
Key press interrupted: cleanup releases tool-owned keys
Repeated key with bounded count: no unbounded input flood
Dead key or compose sequence: defined support or clear unsupported response'''),
('PTR','Pointer and drag','P0','''Single/double/triple click: timing/count tested in real controls
Right-click menu: inspect resulting menu before choosing an item
Hover tooltip: pointer move without accidental click
Wheel scroll vertical/horizontal: correct target under pointer
Nested scrolling panes: verify which pane moved
Smooth scrolling: support or explicit discrete-wheel semantics
Drag within window: interpolate motion and release button on failure
Cross-window drag: source/target identities and changed focus handled
Drag onto file manager: distinguish copy/move/link and confirmation dialog
Invisible overlay intercepts click: do not equate input dispatch with target activation'''),
('WAIT','Waiting and synchronization','P0','''Window appears: condition-based bounded wait
Element appears/disappears: fresh tree and explicit timeout
Text equals/contains: exact condition with truncation considered
Busy UI stops responding: timeout remains bounded
Animation after click: settle condition rather than guessed fixed sleep
Debounced text update: wait for readback within a defined deadline
Long save operation: verify completion rather than button dismissal
Clipboard readiness: wait for ownership before input
Cancellation while waiting: no further input after cancellation
Clock change: use monotonic deadlines'''),
('ERR','Errors, retries and outcomes','P0','''Precondition failure: effect=none only when no input was sent
Dispatched input: never labelled verified application success
Exact readback: state what condition was actually verified
Mid-action timeout: uncertain outcome, no automatic mutation retry
Partial compound action: identify completed portion and remaining uncertainty
Backend exception: structured bounded error without server crash
Client retries same request: idempotency policy for non-idempotent operations
Unknown error: conservative effect classification
Failed cleanup: surface stuck-input risk and recovery instructions
Recovery attempt: inspect state before repeating Save/Send/Delete/Submit'''),
('CONC','Concurrency and input ownership','P0','''Two MCP clients: serialize display mutations across processes
Two threads: reject busy mutation predictably
Independent displays: locks do not block unrelated desktops
Lock-holder crashes: operating system releases lock
Human uses viewer simultaneously: declared policy and takeover mechanism
Agent has long drag: human interruption cancels and releases button
Fairness: busy client cannot starve all other clients indefinitely
Read observation during mutation: consistent snapshot or declared inconsistency
Stale queued action: revalidate when lock acquired
Multiple agents share clipboard: no false ownership/verification claims'''),
('SEC','Local trust and data handling','P0','''Desktop worker runs as ordinary desktop user, not root
Session selection: do not read another account's desktop accidentally
No shell interpolation: arbitrary text remains data
Runtime directory: private ownership, permissions and symlink checks
No unauthenticated network control listener by default
Text/screenshots not logged or uploaded by default
Secrets in errors: bounded diagnostic without full payload
Untrusted UI instruction: skill treats it as application data, not new user authority
Target protected field: explicit capability boundary and redaction
Dependency supply chain: pinned reproducible install and reviewed artifact provenance'''),
('DIAG','Diagnostics and observability','P0','''Doctor checks actual display access, not only environment variables
Doctor checks actual accessibility bus/provider response
Per-capability readiness: partial support not flattened into all-ready
Errors identify missing dependency without requiring traceback interpretation
Action timing: measure latency without recording text payload
Optional trace: explicit local retention and deletion rules
Trace correlation: observation/action IDs connect steps without leaking secrets
Mismatch report: expected/actual length/hash without mandatory plaintext dump
Resource usage: monitor orphan workers and clipboard owners
Bug reproduction: export minimal sanitized environment and steps'''),
('PERF','Performance and resource bounds','P0','''Tool list: compact enough for agent discovery without hundreds of redundant actions
Idle server: no busy polling of desktop
Screenshot latency: measured budget on ARM64 microsandbox
Accessibility latency: bounded even for broken provider
Action latency: measured separately from application completion
Memory growth: bounded handle caches and image buffers
Very many windows: bounded enumeration and useful truncation
Huge selection/paste: enforce limit before allocating unbounded subprocess buffers
Long session: repeated operations do not leak file descriptors or processes
Low CPU/memory: fail usefully instead of wedging desktop'''),
('FILE','Native file workflows','P0','''Save existing text file: independent on-disk exact-content verification
Save As new path: operate native dialog and confirm actual file
Filename with spaces/Unicode: preserved exactly
Overwrite existing file: inspect confirmation and follow intended operation
Read-only path: observe error and preserve unsaved contents
Disk full: no successful-save claim
Open dialog: locate intended directory/file rather than typing into wrong field
Unsaved close: Save/Discard/Cancel mapped to user's intent
Download chooser: confirm actual destination and completion
Symlink or renamed destination: verify resulting path, not just dialog dismissal'''),
('TERM','Terminal workflows','P0','''Single-line passive reader: exact UTF-8 paste without invoking a shell
Multiline paste confirmation: detect and expose dialog
Bracketed paste enabled: preserve content and distinguish submission
Bracketed paste disabled: warn/contract that newline can execute commands
Tabs in pasted terminal text: not converted to completion key presses
Ctrl+C: distinguish interrupt from clipboard copy
Ctrl+Shift+V: app-specific CLIPBOARD behavior qualified
Shift+Insert: PRIMARY behavior detected and documented
Terminal alternate screen/TUI: screenshot and keyboard interaction supported
Terminal output escape sequences: cannot become tool protocol or new instructions'''),
('WEB','Browser integration','P0','''Headed browser runs in same visible guest desktop
Textarea multiline/tab/Unicode: independent DOM readback exact
Contenteditable field: inserted text and line-break representation verified
Browser shortcut conflict: deliberate keypress not mistaken for text
Native file picker: hand off from DOM tools to desktop tools
JavaScript alert/confirm/prompt: identify modal and intended action
Browser permission dialog: do not silently grant unrelated access
Several profiles/windows/tabs: control correct visible session
Canvas/WebGL page: screenshot fallback remains available
Browser DOM tools unavailable: desktop capability degrades clearly'''),
('APPS','Application compatibility matrix','P0','''GTK editor: edit, save, reopen and verify file
GTK file manager: navigate, select and open synthetic test files
Qt editor/app: text, menus and modal dialog qualified
Electron editor/app: accessibility and clipboard qualified
Chromium: native and web controls qualified
Firefox: text and dialogs qualified independently of Chromium
XFCE Terminal: passive-reader paste and dialogs qualified
xterm: selection/shortcut differences qualified
Image editor/canvas: drag/select/scroll via pixels qualified
App with no accessibility: usable screenshot-only workflow documented'''),
('FAULT','Fault injection','P0','''Kill target app before action: no delivery to replacement app
Kill target app during action: uncertain outcome returned
Freeze target app: control server remains responsive after deadline
Kill accessibility bus: diagnose and reconnect without stale handles
Kill X server: bounded failure and reconnection path
Disconnect SSH: server lifecycle and cleanup tested
Change screen resolution mid-action: reject or report uncertainty
Replace clipboard owner mid-paste: detect or report uncertainty
Fill artifact directory: no global desktop corruption
Restart MCP mid-drag: release strategy tested and limitations documented'''),
('SHIP','Packaging and product acceptance','P0','''Clean install from Silo GUI: desktop and tools appear together
Existing VM upgrade: preserve user desktop/files and add control capability
Fresh Codex remote task: no hand-written environment setup needed
Skill auto-discovery: correct scope and actual tool names
Offline startup after install: no vendor login or model API required
Guest health view: report desktop and tool readiness separately
Human viewer reconnect: same session as agent controls
Version reporting: driver, skill and tool schema identifiable
Reproducible acceptance command: independent observer and recorded failures
Release gate: no claim of production readiness with unqualified P0 cases'''),
('WAY','Wayland and alternative backends','P2','''Wayland session: explicitly rejected until a backend is implemented
Portal permission: no false claim of unattended grant
Remote-desktop portal: session lifecycle and revocation qualified
Compositor-specific input: isolated behind same public contract
XWayland app: do not assume access to native Wayland apps
Headless compositor: supported startup and capture path documented
Wayland clipboard: explicit data-control/portal support
Mixed X11/Wayland: correct capability per target
Selkies viewer: control engine independent of streaming transport
Standard VNC-only client: KasmVNC incompatibility identified'''),
('MEDIA','Optional richer desktop capabilities','P2','''Screen recording: explicit start/stop, bounded storage and privacy policy
Audio playback observation: scoped device capture and timestamps
Microphone input: explicit source and lifecycle
Webcam injection: explicit source and user intent
Touch gestures: coordinate and gesture semantics qualified
Stylus pressure: support or explicit unsupported response
OCR: optional local grounding with uncertainty and source coordinates
Image matching: confidence threshold and stale-image handling
Remote file transfer: separate from GUI action with explicit paths
Multi-user sessions: strict session isolation and independent input ownership'''),
('INTEL','Agent usability and evaluation','P0','''Agent can infer next action from observation without inspecting driver source
Missing accessibility: agent switches to visual mode without invented node IDs
Text failure: agent reads back instead of blindly retyping
Save timeout: agent checks document/file before retry
Stale snapshot: agent reobserves and recomputes coordinates
Paste dialog: agent distinguishes blocked workflow from text loss
Tool error: concise suggested recovery without hiding uncertainty
Token cost: bounded trees and screenshot dimensions evaluated on real tasks
Held-out workflows: evaluate apps/tasks not used to develop the driver
Repeatability: publish successes, failures, versions and environment, not one lucky demo'''),
('STATE','State and handle integrity','P0','''Element expires: reject before invoking application
Server changes: old opaque handles rejected
Role/name changes at same path: identity revalidated
Text read limit: truncation explicit; no false full-value comparison
Window changes title: stable ID preserved when underlying identity unchanged
Tree restructuring: resolve object identity rather than fragile child index
Backend loses node: inspect again rather than broad search-and-click fallback
Observation cache bound: expired entries evicted even in long sessions
Target window moves after semantic inspect: semantics remain scoped or fail safely
Action changes modal topology: old action context invalidated or revalidated'''),
]

GROUPS.extend([
('AUTH','Credentials and authentication UI','P1','''Password entry: explicitly supported secret-input path without plaintext readback or logs
Masked field observation: do not infer hidden contents from placeholder/bullet count
Password manager popup: target correct native/browser UI and preserve user intent
OTP entry: preserve leading zeros and avoid retaining one-time values
Session expiry during workflow: detect login transition rather than act on old coordinates
OAuth new window: identify origin/session and resume the intended application
Credential field blocks clipboard: explicit alternate supported input or limitation
System authentication dialog: distinguish privileged operation from ordinary application input
Screen lock: detect locked session and do not claim normal desktop readiness
CAPTCHA or human-presence step: expose the requirement instead of claiming automation succeeded'''),
('MENU','Menus, popups and transient UI','P0','''Application menu bar: open, inspect, choose item and verify effect
Nested submenu: hover/key navigation with bounded opening wait
Context menu outside client bounds: explicit transient target instead of guessed parent coordinates
Unmanaged X11 popup: associate with owner or declare targeting unsupported
Tooltip overlaps target: avoid interpreting tooltip pixels as the underlying control
Notification steals attention: preserve intended target and report focus change
System tray menu: identify actual app/menu rather than panel-wide blind actions
Tear-off or detached menu: new identity and coordinate context
Menu disappears on observation: reject stale target and reopen deliberately
Default button changes in dialog: deliberate action identity rather than blind repeated Return'''),
('DATA','Forms, tables and virtualized widgets','P1','''Virtualized table rows: scroll and reacquire item identity rather than reuse index
Sorted/filtered list: act on stable item meaning after order changes
Multi-selection: explicit replace/add/range semantics and verify selected items
Editable grid cell: distinguish entering edit mode from replacing whole widget text
Date/time picker: honor locale, timezone and validation
Numeric field: detect formatting, rounding and range constraints
Rich text editor: distinguish plain text content from markup and formatting
Form validation: observe error rather than mistake submit dispatch for success
Auto-complete suggestion: select intended suggestion without losing literal input
RTL layout: visual navigation and text storage semantics remain distinct'''),
('EVAL','Qualification methodology','P0','''Independent oracle: verify app/file/DOM state rather than echo driver arguments
Repeat runs: disclose run count and intermittent failures
Clean guest: reproduce without hidden developer dependencies or prior session state
Version matrix: record distro, architecture, desktop, toolkit, browser and driver versions
Held-out tasks: include workflows absent from implementation fixtures
Negative cases: prove invalid/stale requests do not mutate targets
Timeout tests: inspect late effects after recovery, not only elapsed duration
Performance measurements: report distributions and environment instead of an unsupported speed claim
Evidence retention: synthetic fixtures, failure transcripts and reproducible commands
Release decision: separate implementation coverage, local test evidence and production qualification'''),
])

root=Path(__file__).resolve().parents[1]
catalog={'schema_version':1,'scope':'Silo local Linux X11 desktop; P2 optional expansions','status_policy':'unqualified means no release-level evidence; implementation alone is not qualification','features':[]}
lines=['# Feature and acceptance catalog','', 'This is a bounded engineering catalog, not a claim that all possible GUI states can be enumerated. Extend it for every newly observed failure. P0 is required before declaring the supported product production-ready; P1 is the fuller product surface; P2 is optional expansion. All cases begin unqualified. See VALIDATION.md for the narrower actual test evidence.','']
for key,title,priority,cases in GROUPS:
 feature={'id':key,'title':title,'priority':priority,'cases':[]}
 lines += [f'## {key}: {title} ({priority})','']
 for i,case in enumerate(cases.splitlines(),1):
  cid=f'{key}-{i:02}'
  feature['cases'].append({'id':cid,'acceptance':case,'qualification':'unqualified'})
  lines.append(f'- **{cid}** — {case}.')
 lines.append('');catalog['features'].append(feature)
(root/'docs'/'requirements.json').write_text(json.dumps(catalog,ensure_ascii=False,indent=2)+'\n')
(root/'docs'/'REQUIREMENTS.md').write_text('\n'.join(lines)+'\n')
print(len(GROUPS),'feature groups;',sum(len(f['cases']) for f in catalog['features']),'acceptance cases')
