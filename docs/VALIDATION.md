# Validation and supported scope

Luda is a standalone Linux computer-use plugin, skill and toolset. Completion is judged against supported graphical workflows, not machine provisioning or every desktop configuration.

Demonstrated core behavior includes native X11 observation and targeting; pointer/keyboard input; Unicode and multiline text; accessibility inspection and desired-state controls; windows/workspaces; stale-observation refusal; cancellation and owned-input cleanup; MCP transport; installation integrity; and plugin/skill registration. Optional owned-browser workflows have separate HTML and cooperating-editor evidence.

The tested baseline is Ubuntu 24.04 on ARM64 and AMD64 with XFCE/XFWM4 or private Xvfb/XFWM4. Native Wayland/Xwayland are intentionally rejected. Other application providers and X11 window managers are not automatically qualified by those results.

Before the standalone cleanup, source `f7f9853` ran 992 unit tests: 991 passed as root (one unavailable build-dependency skip); 982 passed as the ordinary account (ten environment-dependent skips). These are historical baseline results, not verification of subsequent changes. Final standalone results will be recorded separately.

Known limitations:

- X11 cannot exclude simultaneous human input. State is sampled; a change and reversal entirely between samples can escape detection.
- Native AT-SPI does not provide authoritative generic IME preedit state. Do not claim composition-safe editing for arbitrary native applications.
- An inaccessible or incomplete application provider limits semantic editing. Dispatch-only pointer and keyboard results require application verification.
- Rich-editor control is limited to explicitly supported cooperating providers. Existing arbitrary browser profiles do not gain a DOM provider.
- Authentication dialogs and lock screens are not universally classified or automated.

Product defects are failures of documented contracts. Test-harness defects concern fixtures, timing, cleanup or evidence collection and are recorded separately; fixing a harness does not diagnose a historical product failure. Unsupported environments produce capability errors rather than new architecture requirements.

The [existing acceptance inventory](REQUIREMENTS.md) is retained with sandbox-specific cases removed. Local tests do not automatically qualify an entire requirement. Historical reports and original failures remain in test evidence or Git history; they are not current installation instructions or release gates.

## Standalone acceptance

Source `830a3c4` passed [the retained standalone checks](../tests/evidence/standalone-830a3c4/README.md): 920 unit cases (919 root passes, 917 ordinary-account passes, remaining cases explicitly skipped), all 17 private native GUI suites, semantic/workspace regressions, an actual locked installation matching all 50 modules and the skill, and native/MCP workflows through that installed executable. Three build regressions separately passed with locked build tools. Plugin schema validation and actual temporary-profile plugin registration also passed.

This completes local supported-core acceptance. Optional backend CI results are tracked separately. The limitations above remain support boundaries, not open integration projects.
