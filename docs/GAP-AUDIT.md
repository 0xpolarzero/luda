# Current capability and evidence gaps

This audit describes source `5ef173b` on 2026-09-20. Luda has a substantial implemented and locally tested X11 desktop driver; the remaining work is a mix of explicit provider limits, specific missing workflows, broader environment evidence and Silo/Mac integration. It is not yet a qualified release. All 346 catalog cases remain release-unqualified; priorities and acceptance criteria are unchanged.

Read the exact criteria in the [catalog](REQUIREMENTS.md), source-bound results in [validation](VALIDATION.md), and fixture scope in the generated [live inventory](LIVE-COVERAGE.md). The unit map associates 122 requirements with 247 distinct methods; the live inventory registers 55 fixtures with 141 distinct requirement associations. These overlapping counts are inventories, not pass percentages. An unmapped unit requirement can have live evidence, and a registered fixture can expose a failure. No historical run becomes a pass on current source by being listed here.

## Implemented capabilities with scoped evidence

The old audit's missing-feature table is superseded. The following are implemented; their evidence remains bounded by the documented providers, versions and scenarios.

| Capability | Existing evidence and boundary |
|---|---|
| Session attachment, startup readiness, reconnect and invalidation | [Reconnect](RECONNECT.md), [session state](SESSION-STATE.md), [bus generation](BUS-GENERATION.md) and [lifecycle](LIFECYCLE-QUALIFICATION.md) cover explicit account attachment, bounded readiness, replaced sessions/providers and stale handles. They do not establish fresh Mac provisioning. |
| Observation, windows and waits | [Topology](DISPLAY-TOPOLOGY.md), [window discovery](WINDOW_METADATA.md), [waits](WAIT-CONTRACT.md) and [geometry](GEOMETRY-QUALIFICATION.md) cover bounded images, paginated discovery, fullscreen/raise, fresh-tree predicates and sampled pixel stability. Pixel stability is not general application idleness. [Font diagnosis](FONT-RENDERING.md) checks fixed samples, not universal glyph coverage. |
| Input ownership and recovery | [Keyboard](KEYBOARD.md), [pointer input](POINTER-INPUT.md), [public MCP recovery](MCP-INPUT-RECOVERY-QUALIFICATION.md) and [admission](ADMISSION.md) cover owned injectors, controller death, stopped workers, replacement-server protection, explicit recovery, repeated keys and cooperative FIFO admission. Human input is not exclusively owned. |
| Text, semantic actions and target identity | [Provider text review](PROVIDER-TEXT-REVIEW.md), [selection identity](SELECTION-IDENTITY-REVIEW.md) and [activation identity](ACTIVATION-IDENTITY-REVIEW.md) cover exact text checks and changed/reused targets. Provider-specific limits below remain; asynchronous window-manager dispatch is not an atomic generation-bound operation. |
| Clipboard and terminals | [Clipboard](CLIPBOARD-QUALIFICATION.md) covers competing owners, owner death, a manager, slow consumers and PRIMARY preservation. [Terminals](TERMINAL-QUALIFICATION.md) use passive PTY byte oracles for real terminal input. Snapshot preflight does not guarantee atomic clipboard delivery. |
| Native files and applications | [Mousepad](FILE-WORKFLOW-QUALIFICATION.md), [Thunar](THUNAR-QUALIFICATION.md), [symlink/renamed destinations](FILE-DESTINATION-QUALIFICATION.md), [browser downloads](BROWSER-DOWNLOAD-QUALIFICATION.md) and [GIMP](IMAGE-EDITOR-QUALIFICATION.md) have independent file/application oracles. These are concrete workflows, not every application or file-failure mode. |
| Controls, authentication and usability | [Data entry](DATA-ENTRY-QUALIFICATION.md), [controls](DATA-CONTROLS.md), [overlays](OVERLAY-QUALIFICATION.md) and [fresh-agent tasks](AGENT-USABILITY-REGRESSION.md) go beyond generic buttons and scripted text input. [Authentication](AUTH-QUALIFICATION.md) records four scoped successful workflows and retained failed routes; a subsequent OAuth-menu repeat failed, so repeated robustness is not established. |
| Installation, faults and bounded resources | [Installation](INSTALLATION.md), [storage faults](STORAGE-FAULT-QUALIFICATION.md), [resource limits](RESOURCE-LIMIT-QUALIFICATION.md), [error privacy](ERROR-PRIVACY.md) and [plugin packaging](CODEX-PLUGIN.md) cover isolated installs, failure handling, bounded child resources and redacted unexpected errors. An installed-driver regression and hosted AMD64 CI complement local ARM64 evidence; neither substitutes for fresh Silo onboarding. |

## Confirmed limitations and provider boundaries

These are not resolved by rerunning the same successful fixtures.

| Area | Current boundary and remaining work |
|---|---|
| IME composition (EDIT-10) | Real GTK and Chromium probes show no reliable generic pending-composition marker. Existing preedit can be lost or can change text after a seemingly exact read. [Composition evidence](IME-COMPOSITION.md) requires a cooperating/provider-aware solution or an explicit limitation; absence of an IME daemon does not prove safety. |
| Rich editable text (WEB-03, DATA-07) | Embedded hypertext can differ from the DOM's plain-text serialization. Exact generic replacement cannot be verified and is refused where representation is unsupported. [Browser contract](BROWSER-TEXT-CONTRACT.md) documents this boundary; a correct clipboard effect alone does not verify the semantic operation. |
| GTK4 semantic controls | The documented toolkit run retains provider failures for selection/caret, unsupported checkbox actions and blocked dependent cases. Supported insertion and full replacement are separate. [Toolkit evidence](TOOLKIT-QUALIFICATION.md) must not be summarized as universal GTK compatibility. |
| Electron and Firefox text | Electron 44.4.3's Chromium 152 cannot authoritatively verify the tested non-BMP replacement selection and refuses it. Modern Chromium's earlier offset defect was fixed; it is not a current blanket Chromium limitation. Firefox's normalized Unicode selection works, but protected native editing remains unsupported in the tested provider. See [Electron](ELECTRON-QUALIFICATION.md) and [Firefox](FIREFOX-QUALIFICATION.md). |
| X11 concurrency and cleanup | Human input, clipboard ownership and asynchronous WM processing can change after checks. Generation-bound input and conservative uncertainty narrow these races; they do not provide exclusive human ownership or app-level transactions. An unavailable/stalled original server can leave recovery pending. |
| Display-driver coverage | Real logical-monitor/CRTC changes and panning have evidence. The tested Xvfb, Kasm and dummy drivers refuse the attempted rotation/transform configurations. [RandR review](RANDR-BACKEND-REVIEW.md) distinguishes that limitation from implemented metadata/invalidation and verifies explicit refusal when RandR is absent. Physical mixed-DPI, fractional scaling and rotated outputs need a capable backend. |

Some criteria expressly accept a clear unsupported boundary. That permits an honest response contract; it does not mean the requested application workflow succeeded or that the whole case is qualified.

## Remaining locally testable evidence

Existing adjacent tests should be reused, without treating them as substitutes for these cases:

- **Native save on full storage (FILE-06):** helper startup/screenshot ENOSPC and readonly editor saves exist. A real editor's full-disk Save, visible error, retained dirty buffer and recovery are not established.
- **Client transport loss during mutation (MCP-08):** protocol cancellation, controller death and recovery have tests. Actual client EOF without a cancellation message needs its own cleanup/no-replay oracle. A real SSH disconnect (FAULT-06) is a separate transport/lifecycle experiment, feasible with an owned local SSH setup; it is not inherently Mac-only.
- **File-manager drag intent (PTR-09):** custom GTK cross-window drag and Thunar clipboard workflows do not establish copy versus move versus link, native confirmation, or Cancel during a real file-manager drag.
- **Uncovered interaction variants:** nested scrolling panes (PTR-05), system-tray and detached menus (MENU-07/08), password-manager and system-authorization surfaces (AUTH-03/08), clipboard-blocking credential fields (AUTH-07), and RTL visual navigation (DATA-10) need scoped fixtures or real-app evidence. Existing authentication work does not cover those credential paths.
- **Input and provider breadth:** current layouts, repeat and held-input tests do not establish all compose/dead-key behavior (KEY-10), every toolkit version, or resolution of the concrete limitations above. Record supported/refused behavior rather than guessing from toolkit names.
- **Duration and resource breadth:** child RLIMIT_NOFILE/RLIMIT_AS failures and bounded operation loops do not establish hours-long sessions (PERF-09), full low-CPU/memory behavior (PERF-10), host OOM behavior or every disconnect interleaving. Extend only with a stated duration/load and independent resource/effect oracle.
- **Agent usability breadth:** real fresh-agent tasks already exist. Additional held-out workflows and repetitions must expose tool-selection friction and preserve first failures, not merely repeat a known script or infer intuitiveness from unit counts.

## Highest-value next three local tasks

1. **Exercise FILE-06 with Mousepad on a private bounded filesystem.** Create an owned small tmpfs in a private namespace, save a baseline, then attempt a larger edited buffer when space is exhausted. Drive the visible Save/error UI through public tools. Independently check original bytes, unsaved buffer retention and lack of a successful-save claim; free only fixture-owned space and verify an exact subsequent save. Never fill the host filesystem. This closes a real application-effects gap left by helper fault injection.
2. **Exercise MCP-08 with a real disconnected stdio client.** Start an owned server and application, interrupt transport during a provably started mutation without sending protocol cancellation, and bound shutdown/recovery. Independently observe owned held-input cleanup, process lifetime and absence of late/replayed effects. Reattach with a fresh server and verify old handles are rejected. Keep this result distinct from SSH-network qualification.
3. **Exercise PTR-09 with two owned Thunar locations.** Perform copy, move and link drags with explicit modifiers, plus a native conflict/confirmation Cancel path. Use independent source/destination bytes, inode/link targets and unchanged-state oracles. Preserve ambiguous or unsupported outcomes. The purpose is to establish operation intent and confirmation handling, not another generic drag success.

These are evidence tasks, not assertions that the driver needs three new APIs. A demonstrated defect should produce a narrow regression and fix; an application/provider limitation should remain explicit.

## External product and environment evidence

The following require the actual product/host environment, rather than another Linux guest unit test:

- Fresh ARM64 and AMD64 microsandbox images (ENV-01/02, EVAL-03), including installation without inherited session configuration. Hosted AMD64 Linux is useful but is not microsandbox.
- Silo's clean provisioning and existing-VM upgrade flows (SHIP-01/02), preserving user files and desktop settings.
- Fresh Mac Codex SSH attachment and automatic tool/skill discovery (MCP-01, SHIP-03/04). Generated config, temporary local plugin registration and guest-side execution are not proof of host discovery or remote placement.
- Silo's separate desktop/tool health reporting and a human viewer reconnecting to the exact agent-controlled session (SHIP-06/07).

A capable multi-monitor/rotation backend is another environment gap, but it is independent of Mac onboarding and can be investigated locally if suitable hardware or a driver is available. No new confirmation is required merely to continue authorized local work.

## Historical provenance and release interpretation

The [previous accumulated audit](GAP-AUDIT-HISTORY.md) is preserved as a historical record, including its superseded missing-feature claims. The [first broad matrix record](QUALIFICATION-MATRIX.md), [older unit snapshot](UNIT-COVERAGE.md), [newer scoped unit snapshot](UNIT-COVERAGE-CURRENT.md) and [live association corrections](LIVE-MAPPING-AUDIT.md) retain their own source and scope. They are not a combined current passing run.

Keep raw failures and original artifact labels. Authentication's explicit required-workflow/diagnostic-route policy must not hide a failing required workflow; its first scoped pass is not repeated qualification. Do not downgrade priorities, remove difficult cases or mark catalog cases qualified from this audit. Report implemented behavior, actual matching-run evidence, explicit limitations and missing evidence separately.
