# Candidate status: not ready to replace the default backend

This branch implements private XI2 input behind the existing tools. It is kept
separate from main because compatibility testing found a native keyboard
regression in Chromium 153. Do not interpret the GTK fixture passes as full
computer-use qualification.

## Established behavior

- Nine public MCP cases pass on GTK3/XFWM: actual click, hover, wheel, drag,
  native text, held human inputs, simultaneous typing, menus, visible overlay
  pixels, and stale-observation refusal. Independent app files verify effects.
- Session-owned input validates pair identity and connection binding before each
  event. No native injector falls back to human devices. Crash and removed-pair
  cleanup tests preserve matching human-held keys and buttons.
- Restoring minimized GTK windows requests no initial focus; the retained
  continuous human-typing fixture passes. Existing tool signatures are unchanged.
- Owned Chromium text and selection operate through its addressed page without
  foregrounding it. The browser suite passes its first 27 checks, then fails the
  native IME precondition because private keyboard events produce no DOM input.
  The remaining dependent suite cases were not executed on this candidate.

## Release blockers and limits

1. **Chromium native keys:** the private native route does not produce browser key
   events in the tested configuration. Ordinary shortcuts, paste through native
   chords, and native IME cannot be claimed working. Do not report dispatch as an
   application effect. Core-enabled private events, targeted core synthetic events,
   and scoped application ClientPointer reassignment did not fix the retained
   probe. See [pinned source research](chromium-native-compatibility.md).
2. **GTK accessibility focus:** its provider explicitly presents the window. That
   callback redirected human typing in a continuous fixture. Private input cannot
   prevent application-issued activation. Substituting a click would change the
   operation's semantics and is deliberately not done.
3. **Viewer cursor behavior:** root-capture overlay pixels are verified, but viewers
   which separately render MPX cursor sprites may show an additional persistent
   native cursor. Native-sprite/viewer combinations are not qualified.
4. **Broader compatibility:** Qt, GTK4, other WMs and legacy clients have not been
   qualified for this candidate. Native Wayland remains unsupported. Clipboard
   state is shared. An abruptly killed restore helper may leave a zero user-time
   property until the application updates it; normal failures restore it.

The requested combination of fully working general computer use and no human
input takeover is therefore **not complete**. No shared-device fallback, alternate
agent tool set, viewer integration, or window-manager replacement was added to
hide those limits. This branch is reviewable work, not a production release.

## Evidence

Final integrated run: **950 unit tests passed, one optional build test skipped**;
all nine public input cases and the cursor/lifecycle/removed-device checks passed.
[Final revision and runtime hashes](final-validation.json) bind these results to
the tested source. The browser failure remains a release blocker.

- [Public tool and ownership checks](README.md)
- [Focus/restore fixtures and counterexamples](../isolated-focus/README.md)
- `owned-browser.json.gz`: actual passing cases and failed native-IME oracle,
  captured on the integration worktree with Chromium 153.0.8010.12 as an explicitly
  selected ordinary test account. No shared desktop or real user content used.
