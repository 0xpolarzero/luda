# Remaining P0 work after managed-browser and rich-clipboard integration

Read-only audit of `7783721`, 2026-09-20. Acceptance text and priorities come from
[requirements.json](requirements.json); all 346 cases remain release-unqualified.
This report identifies nine concrete work items, not nine newly reproduced bugs.
It distinguishes missing behavior, deliberately limited providers, missing local
assertions, and tests that need another environment. An absent unit association
is not evidence that a feature is absent.

The [current source-bound record](UNIT-COVERAGE-CURRENT.md) already includes the
775-test snapshot, ordinary-account results, actual installed-wheel equality,
poisoned-PYTHONPATH installation, native/HTML browser runs, and 46 rich-clipboard
assertions. The [live inventory](LIVE-COVERAGE.md) lists fixtures, not passes.
Earlier native-input, installer, and clipboard-guardian failures remain retained;
those fixed failures are **not** listed as current blockers here.

## Confirmed implementation or provider limitations

| Case and acceptance | Actual remaining gap | Next concrete work |
| --- | --- | --- |
| **EDIT-10:** active IME must be explicitly completed/cancelled or conflicting input refused | The generic native backend still cannot determine current preedit. [Real GTK probes](IME-COMPOSITION.md) found Entry focus/type clearing preedit and TextView exact readback succeeding while preedit survived and later committed. The optional owned-browser guard solves a different, explicitly owned scope. `Desktop.doctor` and the skill disclose the generic limitation; disclosure does not implement refusal. | Resolve a native composition capability contract before claiming universal native typing: an application-cooperating current-state adapter must bind the exact field and preserve active preedit, or the unsupported scope must remain explicit. Reuse `live_ime.py` as the independent preedit oracle; do not infer state from engine presence or a successful Unicode paste. |
| **ERR-05:** identify completed portion and remaining uncertainty after a partial compound action | The [unit map](test-map.json) already calls this partial. The browser worker verifies intermediate rich segments but serializes errors as code/effect/clipboard possibility without completed-segment metadata. Repeated native chords report `dispatched_count` on full success, but an interrupted repeat has no completed-count report. Conservative uncertainty prevents false success, but does not tell the agent what was completed. See [_browser_worker.py](../src/luda/_browser_worker.py), [_keyboard_native.py](../src/luda/_keyboard_native.py), and the real partial-input cancellation oracle in [live_owned_rich_clipboard.py](../tests/live_owned_rich_clipboard.py). | Add bounded, payload-free progress for steps whose completion was actually observed, with the current step explicitly uncertain. Test a known first completed segment followed by a rejected second segment, and a repeated chord interrupted between repetitions. A cancelled client need not receive an invented final response; do not infer completion from queued bytes. |
| **EDIT-03 / TXT-09**, with **APPS-04:** exact selection/empty replacement in the declared Electron matrix | The [actual Electron 44.4.3 suite](ELECTRON-QUALIFICATION.md) remains 15/16: non-BMP clearing cannot be verified because its Chromium152 accessibility selection representation loses information. Runtime refusal preserves text, so this is a supported-provider completeness limit, not silent data loss. Ordinary BMP edits and clipboard text already pass. Owned Chromium153/ProseMirror success does not qualify an unrelated Electron application. | Use the retained Electron DOM/file oracle to qualify a deliberately supported GUI/native route for non-BMP replacement, or a specifically versioned provider update. Never invert the lossy offset conversion or silently retry after selection effects. Retain the failing required case until the actual Electron route succeeds. |

## Missing assertions that can be tested in this Linux VM

| Case and acceptance | Existing evidence is narrower | Next concrete test |
| --- | --- | --- |
| **WEB-07:** browser permission dialog must not silently grant unrelated access | `live_browser.py` covers JavaScript dialogs and native pickers. Owned-browser fixtures cover fields, frames, lifecycle and downloads. No existing fixture assertion found requests and denies an actual browser permission prompt. Generic window/focus safety is not that application workflow. | Use an owned fresh browser profile and loopback secure-context page requesting one named permission, with no pre-granted context permissions. Drive the visible browser prompt through public tools, explicitly deny/dismiss it, and independently verify the permission state and absence of the protected callback. Do not use a fake HTML dialog or require a real camera/microphone. |
| **INTEL-04 / INTEL-06:** agent checks after save timeout; agent distinguishes a blocked paste dialog from text loss | [Fresh-agent recovery](AGENT-USABILITY-REGRESSION.md) tested an unsaved-close warning and successful save. Terminal fixtures test actual multiline confirmation. Neither establishes how a fresh agent handles an uncertain save that later completes, or a paste confirmation with unchanged destination text. | Give one fresh agent an owned delayed-save workflow and another a real terminal paste confirmation with a passive reader. Grade first attempts: no duplicate save/submit, independent file or PTY bytes, explicit dialog handling, and retained failure trace. Keep fixture setup/oracles unavailable to the agent. |
| **SHIP-05:** offline startup after installation without vendor login/model API | Locked installation, local HTTP fixtures and explicit no-startup-download code are useful evidence. The installed managed smoke still runs in a network-capable environment; “local fixture” is not a denied-network experiment. No network-namespace refusal test was found. | Start an already installed wheel and private desktop in an isolated network namespace with no external route, retaining loopback for a synthetic page if needed. Exercise MCP initialize/doctor/observe/native editing and optional preprovisioned browser editing. Assert installed imports and no bootstrap/download/auth prompt. This tests tool startup, not whether a cloud coding agent itself works offline. |

## Delivery work and genuinely external acceptance

| Cases | What is missing | Required environment or deliverable |
| --- | --- | --- |
| **SHIP-01 / SHIP-03**, also **LIFE-01 / SEC-10:** shipped GUI setup and fresh-task discovery | The [Silo integration](../integrations/silo/README.md) is a reviewed patch series. Its canonical `guest/agent-tools-release.json` is still `enabled: false`. Maintainers must configure a real trusted source archive; optional browser configuration additionally assumes a browser distribution already exists in the guest. This is missing product delivery, **not just missing Mac test evidence**. | Produce a versioned source artifact and provenance, configure the architecture-appropriate guest release/browser inputs, and integrate the patch into the actual Silo product. Linux can prepare and verify those deliverables; it cannot claim their macOS product installation happened. Do not enable a placeholder manifest or label a locally hashed executable independent supply-chain verification. |
| **ENV-01 / ENV-02 / MCP-01 / SHIP-02 / SHIP-04 / SHIP-07 / EVAL-03:** fresh guests, real remote discovery, upgrade, and same-session viewer | Hosted AMD64 and this ARM64 guest, private SSH transports, private Codex registries, Rust/frontend integration tests, and installed wheel tests are already meaningful. They do not create a fresh microsandbox from the shipping Mac app or prove the Mac task loaded the intended skill. | On an owned Mac/Silo environment, create a clean guest for each supported architecture, install through the GUI, attach a fresh Codex task, verify tool/skill identity, make an independently observed edit, reconnect the viewer to that same session, and upgrade while preserving owned documents. Record first-attempt failures. This requires host/product access, not another identical Xvfb run. |
| **LIFE-07 / LIFE-08** and display-specific **GEO-06 / GEO-08 / GEO-10:** suspend/shutdown and supported topology changes | Clock-injection tests and real X-server/process loss are not VM suspend/shutdown. Logical monitor changes, controller movement and panning already have real evidence. [Backend probes](RANDR-BACKEND-REVIEW.md) could not apply rotation/affine transforms on tested Xvfb/Kasm/dummy drivers. | Suspend/resume or shut down an owned disposable VM from its host while a request is active; require stale-handle refusal or uncertain connection-loss outcome, not a guest response after power loss. Use a capable display backend for real rotated/mixed-DPI/hotplug scenarios only if claiming those modes. GEO-06/GEO-08 explicitly permit unsupported results: implementing every physical transform is not an added requirement. |

## Best next bounded local tasks

1. **ERR-05 progress:** expose only already verified/dispatched substeps and explicitly
   unknown current work; test public failure responses without retaining text.
2. **SHIP-05 offline installed startup:** use the now-correct installed-wheel
   provenance checks under denied external networking, not another editable run.
3. **WEB-07 permission intent:** actual browser prompt, explicit refusal, independent
   permission/callback oracle. This requires no personal account or hardware.

Native IME remains the most important unresolved behavioral contract, but another
plain Unicode test will not resolve it. Silo artifact/product delivery can proceed
in parallel with these tests; fresh Mac acceptance cannot be replaced by them.

## Avoid stale or inflated gap claims

- Arbitrary selected-range **cooperating basic ProseMirror** clipboard editing is
  implemented and has model/mark/IME/cancellation evidence. The older GAP-AUDIT's
  blanket middle-selection limitation is superseded. Generic rich editors,
  broader schemas, frames and protected fields remain separate scoped limits.
- Same-root-size logical topology changes are detected now. The final paragraph
  of the older [geometry report](GEOMETRY-QUALIFICATION.md) predates
  [DISPLAY-TOPOLOGY.md](DISPLAY-TOPOLOGY.md); it is not a current runtime defect.
- AUTH is **P1**, not P0. The real system-authentication stack remains absent,
  but AUTH-08 must not be promoted into this P0 list. Its environment report also
  does not mean polkit universally requires macOS or physical hardware.
- Provider criteria that explicitly permit unsupported behavior (for example
  AX-02 and CLIP-09) are not missing implementations solely because refusal is
  their supported result. Conversely, a refusal cannot be reported as successful
  requested text entry.
- No longer-duration soak, universal rich schema, or new hardware support is
  invented here. Priorities, catalog acceptance and qualification status are unchanged.

Follow-up: repeated native key chords now report bounded dispatch progress when a final companion receipt is available. Exact counters distinguish acknowledged dispatches, one possibly partial chord and not-started chords; application effects remain unverified. Tests are mapped narrowly to ERR-05; rich-editor segment progress and other compound actions remain outside that increment. See [keyboard contract](KEYBOARD.md).
