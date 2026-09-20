# Current capability and evidence gaps

Audit refreshed against source `ae824b2` on 2026-09-20. The implementation, evidence and remaining
product work must be assessed separately. The [346-case catalog](REQUIREMENTS.md)
retains its original priorities and acceptance criteria. No case becomes
release-qualified through a passing unit test, a live-suite association or this
audit. The previous [5ef173b audit](GAP-AUDIT-5EF173B.md) and
[earlier history](GAP-AUDIT-HISTORY.md) remain available without rewriting their
source-bound findings.

## Evidence now available

The [current unit record](UNIT-COVERAGE-CURRENT.md) now contains 679 passing root
tests and the matching ordinary-account run (671 passed, eight unavailable Codex
CLI tests skipped). Its map names 136 requirements and 298 distinct unit methods.
These subsequent results retain their own source revision and fingerprint. The [live inventory](LIVE-COVERAGE.md) registers 73 fixtures and
160 distinct requirement associations. These overlap and are not a reliability
percentage or evidence that all associated requirements passed.

Both hosted workflows passed at `8dd8aef`, including independent AMD64 unit,
headless-X11 and native-application jobs. Local evidence uses the ARM64 Silo guest
and private ordinary-account desktops. [Validation](VALIDATION.md) retains the
exact versions, source revisions, source fingerprints and known failures.

The former “next three local tasks” are completed as scoped experiments:

| Workflow | Actual result and limit |
|---|---|
| Native full-disk save | [Mousepad ENOSPC](DISK-FULL-SAVE-QUALIFICATION.md) exposed a real application data-loss failure: the original file became empty. Its dirty buffer survived and explicit recovery saved exact text. No false save-success claim was made. |
| Transport loss during mutation | [MCP EOF](MCP-DISCONNECT-QUALIFICATION.md) and [real local SSH loss](SSH-LOSS-QUALIFICATION.md) observed cleanup and no replay. Partial key delivery and an application callback completing after disconnect remain effects, not rolled-back operations. |
| File-manager drag intent | [Actual Thunar copy/move/link/Cancel](THUNAR-DRAG-QUALIFICATION.md) verifies bytes, inode relationships and symlink targets. It does not establish every theme or cross-filesystem drag. |

Other additions now have their own evidence: [nested panes](NESTED-SCROLL-QUALIFICATION.md),
[tray menus](TRAY-QUALIFICATION.md), [detached menus](DETACHED-MENU-QUALIFICATION.md),
[RTL navigation](RTL-QUALIFICATION.md), [single-line newline behavior](SINGLE-LINE-QUALIFICATION.md),
[undo grouping](UNDO-QUALIFICATION.md), [actual curses interaction](TUI-QUALIFICATION.md),
[stopped-provider deadlines](AX-DEADLINE-QUALIFICATION.md),
[explicit GTK4 GUI alternatives](GTK4-GUI-WORKFLOWS.md), and
[first-attempt agent file organization](AGENT-FILE-USABILITY.md).
These do not erase their documented unsupported routes or first failures.

The [guest bootstrap](GUEST-BOOTSTRAP.md) now composes Silo status preflight,
versioned installation, locked release/readiness validation and a fresh remote
configuration/skill bundle. It was used for a real root installation and upgrade
with system provisioning skipped; the installed runtime passed 31 native and
18 MCP checks on KasmVNC as UID 1001. Both release payloads matched their manifests.
This is working guest setup, not automatic host-side registration.

[Sanitized reports](BUG-REPORT.md) and [driver/tool/skill identities](COMPATIBILITY.md)
now have unit, live MCP and installed-wheel evidence. [The current unit record](UNIT-COVERAGE-CURRENT.md)
also retains the corrected generated-inventory failure instead of omitting it.

## Concrete unresolved behavior

| Area | Remaining boundary |
|---|---|
| Active composition, EDIT-10 | [Real GTK/Chromium probes](IME-COMPOSITION.md) expose lost or later-committed preedit. Generic AT-SPI does not supply authoritative current composition state. A production cooperating adapter is still absent. [Owned-browser prototypes](OWNED-BROWSER-CANCEL-PROTOTYPE.md) now qualify narrow explicit cancellation correlation while retaining unknown and uncertain cases; engine activation or daemon presence is insufficient. |
| Rich text, WEB-03/DATA-07 | Opaque embedded-object text cannot establish exact logical plaintext. Both native and clipboard paths now refuse unsupported representations before mutation and report uncertainty if they arise afterward. This fixes false verification. A [test-only ProseMirror adapter](OWNED-RICH-EDITOR-PROTOTYPE.md) preserves exact paragraph-separated text in its declared route, but broad paste, hard-break, formatting and IME recovery failures remain; no production adapter is inferred. |
| Provider-specific semantic controls | GTK4 selection/caret and checkbox actions, some Qt combo actions, Electron non-BMP selection verification and protected Firefox editing retain explicit limitations. Tested GUI alternatives do not relabel semantic support. |
| Content/session identity, AUTH-05 | A screenshot token validates age, native identity/layout and related checks, not unchanged control meaning. The retained old-login screenshot diagnostic did activate a replacement control. Fresh semantic inspection avoided it in the separate workflow. [Authentication evidence](AUTH-QUALIFICATION.md) and skill guidance preserve this distinction. |
| Input and application races | X11 does not give exclusive human-input ownership, atomic clipboard delivery or application transactions. Successful dispatch is not task completion, and cleanup cannot undo an application effect. |
| Uninspectable installer children | Bootstrap cannot attribute a newly appearing unreadable process safely. It reports cleanup unconfirmed and forbids automatic retry rather than killing an unattributed process or claiming no effect. This is a declared recovery boundary, not successful containment. |

## Additional scoped evidence

The following subsequent experiments add bounded evidence:

- **KEY-10:** the subsequent [dead-key/Compose run](DEAD-COMPOSE-QUALIFICATION.md)
  now establishes nine scoped refusal/recovery assertions through actual MCP,
  independent widget/key-state oracles and exact private layout restoration.
  It qualifies the named refusal route, not composition support.
- **AUTH-03:** the subsequent [KeePassXC run](PASSWORD-MANAGER-QUALIFICATION.md)
  establishes seven native entry-menu checks with two synthetic entries, a decoy
  window, clipboard and vault-file oracles. GUI unlocking, auto-type and browser
  extensions remain outside that result.
- **PERF-10:** the subsequent [CPU-pressure run](CPU-PRESSURE-QUALIFICATION.md)
  adds eight assertions under measured one-CPU contention to the existing
  [memory/descriptor evidence](RESOURCE-LIMIT-QUALIFICATION.md). No system-wide
  OOM, swapping or arbitrary low-resource interleaving is inferred.

These investigations were started after this audit snapshot; only the explicitly
linked completed results above are reported as passes. Broader provider/application combinations and unseen
agent tasks also remain unqualified. Additional work should name the missing
assertion and independent oracle, rather than simply repeat existing passes.

[The sustained MCP run](MCP-SOAK-QUALIFICATION.md) already covers 600.270 seconds,
399 cycles and 2,120 requests with observed resources and clean shutdown. The
PERF-09 acceptance text does **not** specify a minimum number of hours; the old
audit's “hours-long qualification criterion” was an unsupported extra requirement.
The actual evidence is ten minutes, and no longer duration or universal absence
of leaks is inferred from it.

## Product and environment blockers

- Fresh ARM64/AMD64 microsandbox provisioning and Silo GUI installation/upgrade
  acceptance need the actual product environment. Hosted AMD64 Linux is not a
  fresh microsandbox image.
- The [optional Silo patch](../integrations/silo/README.md) now implements guest
  bootstrap invocation and separate tools status/UI against pinned Silo source,
  with actual Linux Rust/frontend tests and real HTTPS/bootstrap composition.
  It remains unapplied to the product and disabled until a trusted release
  artifact is configured. The [host SSH plugin utility](HOST-REGISTRATION.md) now provides explicit selected-profile registration with VM-specific resolved server keys. The native Silo patch now adds discovery, Browse, registration, explicit disconnect/reconnect and reviewed same-transport version updates. Actual generated SSH transports have separate private-session evidence; fresh Mac/Silo acceptance remains external.
- Actual Mac Codex SSH placement, tool/skill discovery, human viewer continuity
  and reconnect require host access. A specific macOS runner/workspace has been
  requested; this Linux guest cannot establish those outcomes.
- [System authentication](SYSTEM-AUTH-ENVIRONMENT.md) is blocked by the absent
  authority/agent stack in this guest. A fake ordinary dialog is not a substitute.
- Physical mixed-DPI/rotated outputs need a capable display backend. The tested
  Xvfb/Kasm/dummy configurations refused the physical transforms; logical monitor
  changes and panning have separate evidence.

No priorities or acceptance criteria are downgraded here. A requirement that
explicitly permits unsupported behavior still needs evidence for that refusal;
its requested application effect must not be described as successful.

[Optional local OCR](OCR.md) is now implemented, with bounded historical screenshot storage, uncertain word candidates and real GTK/MCP geometry evidence. Audio/video capture and other richer media capabilities remain separate work.
