# Basic requirement association audit

Review against source `ecadb3e` considered the 18 requested P0 criteria below.
This changes evidence associations only: no new tests, runtime behavior, catalog
acceptance, priorities or qualification states. The mapping's new `partial`
implementation assessments describe the narrow reviewed boundary; they do not
assert that the corresponding full environment has been qualified.

## Added associations

| Criterion | Actual assertion and scope |
|---|---|
| ENV-03 | `SessionLaunchTests.test_privilege_drop_precedes_exec_and_environment_is_allowlisted` checks groups/GID/UID before exec and excludes unrelated environment values; `test_unrelated_account_cannot_attach` rejects a foreign UID. Syscalls/account resolution are mocked, not real SSH. |
| ENV-04 | `SessionLaunchTests.test_desktop_account_executes_without_privilege_calls` checks same-account exec without privilege calls. No rootless SSH transport is exercised. |
| ENV-05 | `SessionDiscoveryTests` exact-session, missing-environment and missing-explicit-PID methods use synthetic proc entries and `DISPLAY=:7`, reject incomplete state and prevent fallback. They do not test a host's SSH setup. |
| ENV-07 | `SessionLaunchTests.test_missing_authority_prevents_exec` covers only missing-file preflight. Stale-cookie rejection and redaction are explicitly outside this method's evidence. |
| ENV-09 | `SessionWaitTests` cover missing-then-ready, ambiguity without retry, and bounded/zero timeout using mocked discovery/clock. No fresh desktop startup latency claim. |
| DIAG-02 | `DoctorEnvironment.test_malformed_provider_count_is_redacted_and_not_ready` rejects malformed/negative provider replies and redacts them. Actual bus/provider responsiveness remains separate. |
| DIAG-03 | Five `DiagnosticCapabilities` methods distinguish missing AX, keyboard/display, topology and paused/unavailable control while preserving observation and application-dependent editing. These assert classification, not real provider availability. |
| WIN-02 | Three `ProviderScope` methods select the correct same-PID root/provider despite colliding names/paths and refuse a vanished provider. Synthetic trees do not prove every toolkit's top-level mapping. |
| WIN-09 | Activation generation-change and failed post-dispatch lookup assertions preserve stale/uncertain outcomes; the repeated enumeration-race assertion bounds retries. No atomic WM dispatch guarantee. |
| WIN-07 | Registered `live_interaction.py` explicitly minimizes/restores with verified results, then activates and observes the owned window. Added to its existing supplemental live metadata. |
| CLIP-03 | Registered `live_clipboard_interference.py` explicitly records `starts-with-no-clipboard-owner`, then pastes exact multiline Unicode into the independent slow-consumer oracle. Added to its matrix declaration, the single source for that suite's IDs. |

Exact unit method identifiers and limitations are in [test-map.json](test-map.json).
Live associations and scope are generated in [LIVE-COVERAGE.md](LIVE-COVERAGE.md).
No historical artifact is read or promoted to a current pass by these changes.

## Deliberately not associated in this review

- **DIAG-01:** a happy-path doctor result or mocked display metadata is not a
  direct assertion that actual access failure overrides present environment
  variables. No new association from adjacent tests.
- **DIAG-05:** timing-related implementation and privacy checks are not an exact
  combined assertion of action latency reporting without text payloads.
- **WIN-01:** provider-local colliding accessible names are not a substitute for
  duplicate real window titles and stable window identity.
- **WIN-08:** the live interaction suite assigns/switches the already current
  workspace. It does not prove activation from another workspace.
- **AX-07:** generic subprocess deadline tests do not alone establish a hung
  accessibility provider's end-to-end bound.
- **AX-08:** a foreign-provider child marked incomplete is not a defunct child
  encountered during traversal.
- **CLIP-02:** exact consumer output and replaced-owner refusal are useful
  adjacent evidence, but neither isolates exact UTF-8 pre-dispatch byte checking.

These omissions mean this bounded review found no sufficiently direct mapping,
not that the capabilities are absent or that no future review can find evidence.

## Validation

Actual unittest discovery found 565 methods. All 264 distinct references across
131 mapped requirements resolve to discovered methods. The 22 distinct unit
methods used in the nine new unit associations passed. Eight qualification-report
contracts and eight live-inventory contracts also passed. The live inventory was
regenerated and its drift check passed; it lists 60 registered fixtures and 149
associated requirement IDs at this source. Counts are not coverage percentages.
The catalog's 346 release qualification states remain unchanged.
