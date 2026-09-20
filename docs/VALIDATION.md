# Implementation and validation status

Luda remains under active development, not release-qualified. Local evidence comes from an ARM64 Ubuntu 24.04 Silo guest with XFCE/X11 and KasmVNC 1.5.0, plus private Xvfb/XFWM4 sessions. Hosted Ubuntu AMD64 CI runs independent unit, headless and native-application suites. Each suite's account, source and environment matter; these are not interchangeable environments.

The [346-case catalog](REQUIREMENTS.md) defines acceptance targets. [Qualification records](QUALIFICATION.md) distinguish implementations, narrow test assertions, provider limitations and external product acceptance. Test counts are not a reliability percentage.

## Working capabilities and limits

| Capability | Evidence | Remaining boundary |
|---|---|---|
| Attachment and reconnect | Privilege drop, explicit same-account XFCE selection, bounded readiness; one MCP connection survives actual private display/bus/session replacement | Fresh Mac SSH onboarding and fresh microsandbox provisioning remain external |
| Agent protocol | Actual stdio initialization/tools/images/errors/cancellation; strict raw schema validation; safe repair hints | Client timeout need not cancel; acknowledgment may precede cleanup |
| Targeting | Process/start identity plus native X-resource generation; actual same-XID reuse; private provider and authenticated accessibility-bus generation identities | UI content and human input can change between checks; identical semantic-object reuse remains a limitation |
| Observation and pointer | Decorated/borderless/offscreen/fullscreen geometry, scaled screenshot pixel/pointer oracles, covered-target refusal and nested menus | Logical-monitor changes, same-root controller movement and panning tested separately; physical mixed-DPI/rotation/transform coverage remains incomplete |
| Text and controls | GTK3 and Qt exact widget readback; Qt UTF-16 normalization; Chromium authoritative selection endpoints; protected input, lists, radio/checkbox/value/expansion | Opaque rich text cannot always supply exact plaintext; GTK4 and Qt combo provider limits remain |
| Clipboard and terminals | Actual competing owners, slow consumers, Clipman, PRIMARY preservation, 300 KB transfer; xterm/XFCE terminal framing and real confirmation cancel/accept | Clipboard transfer is not atomic; dispatched input still needs destination verification |
| Applications and files | Gio discovery/launch; Mousepad save/overwrite/unsaved and symlink/renamed destinations; Thunar file oracles; Chromium download completion; GIMP exported-pixel oracles | Additional application families and failure paths remain unqualified |
| Coordination and cleanup | Shared pause, cooperative FIFO, cancellation/quarantine, owned key/button injectors, explicit cleanup recovery, replacement-server protection, bounded output/caches | Human input is not locked out; arbitrary layouts, OS fault combinations and long-duration soak remain incomplete |
| Installation and packaging | Hash-locked runtime/build tools, atomic release selection, payload integrity, rollback, preservation of modified files, installable Codex plugin tested in temporary registry | Guest image/apt supply chain and host-side remote plugin placement require separate qualification |
| Storage failures | Injected resource failures plus actual private 64 KiB tmpfs ENOSPC/read-only tests; staged clipboard preserves prior owner and cleans failed writes | Not every filesystem/device failure or power-loss point is covered; uninstall is not rollback-atomic |
| Agent usability | Independent fresh agents complete forms, exact Unicode Save As, screenshot-only canvas, nested-menu/unsaved-dialog recovery and one untrusted-document task; repeated form/canvas first attempts pass | Small local sample and unknown resolved default model; no broad success-rate or injection-resistance claim |

## Reproducible evidence

- `scripts/qualify.py`: named unit evidence linked to requirements. Unit success alone never grants release qualification.
- `scripts/headless_tests.py`: sixteen isolated suites covering native/MCP input, cancellation, controls, menus, geometry, resources, waits, keyboard identity/repetition, input cleanup, server replacement and session-state hints. All sixteen passed locally at `e987d22`; subsequent changes require their own affected checks.
- `scripts/native_app_tests.py`: five isolated ordinary-account suites for Mousepad, Thunar, window states, MCP launches and terminals. Both hosted AMD64 workflows completed successfully at `0cc9fff`, including these suites and desktop contracts.
- Provider suites: `live_semantic.py`, `live_toolkits.py`, `live_controls.py`, `live_combo.py`, and browser suites retain independent widget/DOM oracles and failures. See [toolkits](TOOLKIT-QUALIFICATION.md), [browser](BROWSER-QUALIFICATION.md) and [browser text](BROWSER-TEXT-CONTRACT.md).
- [Reconnect](RECONNECT.md), [clipboard](CLIPBOARD-QUALIFICATION.md), [terminals](TERMINAL-QUALIFICATION.md), [geometry](GEOMETRY-QUALIFICATION.md), [resources](RESOURCE-QUALIFICATION.md) and [storage](STORAGE-FAULT-QUALIFICATION.md) document exact local assertions and limits.
- `scripts/agent_eval.py` requires an already authenticated CLI and explicit private-display opt-in. [Agent evaluation](AGENT-EVALUATION.md) records every retained attempt, independent oracles, trace grading, source hashes and usage.

Generated artifacts are ignored by Git because they can contain synthetic screenshots/text. Unit, headless and native runners reject changing source trees. Re-run affected checks after source changes; historical evidence must not silently become a pass for a newer revision.

### Installed Silo guest smoke, 2026-09-20

Source `c25165c` was installed through the versioned installer into a separate
prefix, producing release `0.1.0-fba39156bb2e560c` and wheel SHA-256
`fed6a3b75e436af96aa18f945ea9dfc4f0ee7e7a126c45f7c7e29898d6e86815`.
The installed launcher dropped privileges to `silo-desktop` (UID 1001) and
attached to the actual Silo XFCE/KasmVNC `:1` desktop at 1440×900. Doctor
reported available XKB, XTest and XI2; screen-lock state remained unknown.
Using that installed interpreter and package, the native fixture passed all
31 assertions and actual stdio MCP passed all 13 assertions, including exact
paste readback. Both runs held the shared desktop test lock and used only
their own synthetic fixture. This establishes a working installed guest build
at that revision; it does not establish fresh Mac provisioning, SSH plugin
discovery or compatibility of later changes.

A second installed regression used immutable source `e64f845`, release
`0.1.0-0f871fc13ac72fc4`, wheel SHA-256
`f1aa443d5a0aef8b4eb33eed91eb78ad5fe19d114745b99d8d6e7be2cff1ffe1`.
The same ordinary-account actual KasmVNC desktop passed all 31 native and
13 MCP assertions again. This wheel includes native pointer movement, compact
monitor metadata, Firefox normalization and table-row selection. Later target
identity and accessible-name changes were not part of that installed revision.

### Installed generation-guard regression, 2026-09-20

Source `f4b23e8` produced release `0.1.0-4bb8f7d8793d6359`, wheel SHA-256
`2134429857071f81713daaa407770dfe6fd41b00ddcad88602287b900da522e3`.
The installed package and launcher passed **31 native and 18 actual MCP checks**
on the ordinary-account KasmVNC `:1` desktop under the shared test lease.
This build includes provider/bus generations, exact selection identities, session
blocking-hint preflight, optional sole-action invocation and redacted unexpected
errors. Doctor reported all eight fixed font samples covered; lock hints remained
unknown, not proof of an unlocked desktop. This is another installed-guest proof,
not fresh provisioning or Mac onboarding.

The integrated unit run at `a58441a` passed **551 tests** with an unchanged source
fingerprint. The newer scoped records include [locale forms](DATA-ENTRY-QUALIFICATION.md),
[fresh-agent locale use](AGENT-LOCALE-USABILITY.md), [tables](DATA-CONTROLS.md),
[overlays](OVERLAY-QUALIFICATION.md), [image editing](IMAGE-EDITOR-QUALIFICATION.md),
[download completion](BROWSER-DOWNLOAD-QUALIFICATION.md),
[resource limits](RESOURCE-LIMIT-QUALIFICATION.md),
[bus generations](BUS-GENERATION.md), [selection identities](SELECTION-IDENTITY-REVIEW.md),
[detached menus](DETACHED-MENU-QUALIFICATION.md),
[nested pane scrolling](NESTED-SCROLL-QUALIFICATION.md),
[native full-disk save](DISK-FULL-SAVE-QUALIFICATION.md),
[MCP disconnects](MCP-DISCONNECT-QUALIFICATION.md),
[actual local SSH loss](SSH-LOSS-QUALIFICATION.md),
[Thunar drag choices](THUNAR-DRAG-QUALIFICATION.md),
[tray menus](TRAY-QUALIFICATION.md),
[undo grouping](UNDO-QUALIFICATION.md),
[single-line newline behavior](SINGLE-LINE-QUALIFICATION.md),
[curses terminal interaction](TUI-QUALIFICATION.md),
[stopped accessibility providers](AX-DEADLINE-QUALIFICATION.md),
[GTK4 GUI alternatives](GTK4-GUI-WORKFLOWS.md),
[fresh-agent file organization](AGENT-FILE-USABILITY.md),
[RTL navigation](RTL-QUALIFICATION.md),
[ten-minute sustained use](MCP-SOAK-QUALIFICATION.md),
and [authentication boundaries](AUTH-QUALIFICATION.md). These have distinct source
snapshots and supported scopes; they are not a single universal acceptance pass.

The integrated `6bba43b` unit run passed **607 tests as root** with unchanged
source (`artifacts/qualification/bootstrap-schema-unit.json`). The same source
passed 606 tests as UID 1001, with the unavailable Codex CLI registration test
explicitly skipped. [The bootstrap evidence](GUEST-BOOTSTRAP.md) preserves the
hosted account-assumption failure that led to this dual-account check. Earlier `bba9c45` passed
the ordinary-account actual MCP suite after native representation guards and
compact JSON responses were added, including elapsed time on a real error.
[Error privacy](ERROR-PRIVACY.md) specifies the timing boundary.

The [guest bootstrap](GUEST-BOOTSTRAP.md) subsequently installed source `7294d86`
on the actual Silo desktop; its installed package passed 31 native and 18 MCP
checks as UID 1001. A later root upgrade at `e7fea80` completed with a fresh remote
configuration/skill bundle, verified both installed payloads and preserved the
prior release. These are existing-guest proofs with system provisioning skipped,
not fresh Mac/Silo onboarding. The [live inventory](LIVE-COVERAGE.md) distinguishes
registered fixtures from standalone experiments; its associations are not passes.

Native full-disk saving exposed an application data-loss failure: Mousepad truncated
the existing document to zero bytes while reporting ENOSPC. The buffer survived
and an explicit retry recovered it after space was freed. Luda reported dispatch
only, so FILE-06’s no-false-success criterion held, but the failed preservation
diagnostic remains visible. Browser auth menu repetition also found a varying
last menu item; a screenshot-reviewed route passed two fresh runs after correction.
Neither finding is hidden by a suite count.

The later hosted `696e9d4` run passed native workflows and all input-generation
assertions, but failed while terminating its disposable Xvfb. The bounded fixture
teardown correction is independently tested, including a deliberately stopped
owned server; see [the retained CI investigation](CI-INPUT-GENERATION-CLEANUP.md).
That failure is not hidden by the earlier passing hosted run.

[System authentication preflight](SYSTEM-AUTH-ENVIRONMENT.md) remains blocked by
the absent authority/agent stack in this guest. In contrast, isolated test-only
OpenSSH binaries allowed an actual generated-key loopback transport-loss test,
without changing global authentication configuration. This still does not prove
fresh Mac Codex discovery.

## Confirmed unresolved issues

1. **Active IME composition:** real GTK and Chromium probes show inaccessible or ambiguously exposed preedit, lost pending input, and later commits changing an otherwise verified value. Diagnostics explicitly report unknown composition state. A reliable guard requires a cooperating application-aware adapter; daemon absence is insufficient. [Evidence and API research](IME-COMPOSITION.md).
2. **Generic rich-editor plaintext verification:** Chromium hypertext can omit structural newlines, while clipboard copy can normalize spaces or lose trailing newlines. A dedicated representation-aware verifier is still needed. The existing failure probe remains failing; no trimming or lossy normalization hides it.
3. **Provider inconsistencies:** GTK4 selection/caret defects and unsupported combo actions remain explicit. Screenshot fallback is useful but does not establish semantic compatibility.
4. **Broader qualification:** display topology, keyboard layouts/crash cleanup, long-running load, additional application families, complex data/authentication widgets and unseen agent tasks remain incomplete. Some have working generic primitives without sufficient qualification evidence.
5. **Product integration and external acceptance:** The [optional Silo patch](../integrations/silo/README.md) implements guest installation hooks and separate tools status, but remains unapplied to the product and disabled pending a trusted release artifact. Explicit host tools/skill registration and reviewed updates now have Linux native and actual temporary-profile Codex CLI evidence. Fresh ARM64/AMD64 microsandbox provisioning, Silo installation/health/viewer lifecycle, and actual Mac Codex SSH discovery also require host acceptance; Linux fixtures or generated configuration cannot establish those outcomes.

Native Wayland remains explicitly unsupported; modern Xwayland refusal now has live evidence. Optional local OCR is implemented with its own bounded evidence. Temporary silent screen recording is implemented with its own bounded evidence. Audio, camera input and rich clipboard formats remain separate catalog expansions. The current GUI backend remains XFCE/KasmVNC; Luda controls the desktop already visible to the user.

## Subsequent diagnostics and Silo integration checks

Source `ae824b2` passed 645 root unit tests, and 644 plus one expected unavailable-Codex-CLI skip as UID 1001, with matching unchanged source hashes. The initially stale generated inventory failure and corrected records are preserved in [the current unit record](UNIT-COVERAGE-CURRENT.md). Actual MCP passed 23 checks at this source. [Installed report verification](BUG-REPORT.md) retains the earlier wheel's exact identity and KasmVNC checks.

The [optional pinned-Silo patch](../integrations/silo/README.md) passed 21 guest-wrapper tests, 18 frontend tests, TypeScript checking and six actual Linux ARM64 Rust desktop tests. A separate [real HTTPS/bootstrap composition](SILO-COMPOSITION-QUALIFICATION.md) passed with system provisioning explicitly skipped. The final source distribution was built with hash-locked build dependencies and contained all six integration assets (`artifacts/silo-integration/packaging-ae824b2/`). These are bounded integration results; fresh images, product deployment and Mac host discovery remain unqualified.

## Subsequent host, backend and OCR integration

The [679-test snapshot](UNIT-COVERAGE-0217541.md) records matching root/ordinary source hashes, retained harness failures and exact hosted workflow revisions. [Real private SSH](HOST-PLUGIN-SSH-QUALIFICATION.md) verifies both generated VM commands against distinct owned desktops and exposed the corrected launcher working-directory bug. [Wayland refusal](WAYLAND-BASELINE.md#rejection-fix-qualification) now rejects unsupported sessions before input.

The [Silo integration](../integrations/silo/README.md) provides native registration, read-only discovery, path pickers, disconnect/reconnect, reviewed version updates, actual SSH helper qualification and matching reviewed skill bytes. Its actual temporary-profile Codex CLI, Linux Rust and frontend tests do not establish Mac packaging, real Silo SSH routing or product deployment. The default guest release manifest remains disabled until a trusted source artifact is selected.

[OCR](OCR.md) passed its integrated private MCP workflow, and the ordinary guest MCP suite passed 23 checks. [Rich text](OWNED-RICH-EDITOR-PROTOTYPE.md), [native composition provenance](OWNED-RICH-EDITOR-PROTOTYPE.md) and [explicit cancellation](OWNED-BROWSER-CANCEL-PROTOTYPE.md) remain scoped prototypes with retained failures and uncertain cases. They do not extend the production text support claim.

The subsequent [688-test snapshot](UNIT-COVERAGE-CURRENT.md) and [temporary recording](RECORDING.md) qualify the named local assertions with matching unchanged source fingerprints. The ten-patch integration also synchronizes the recording skill; fresh Silo and macOS acceptance remain outstanding.
