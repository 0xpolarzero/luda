# Explicit owned-browser password entry

`desktop_type_secret(element_id, text)` now also replaces an observed top-level owned Chromium `input[type=password]`. Discovery reports `secret_entry_supported:true`; existing ordinary text support stays false and ordinary read/type/select/focus continue to refuse protected fields. Native protected EditableText providers retain their existing implementation. No new tool, clipboard fallback, submission, model API or credential store is introduced.

The owned route uses private metadata only: exact node/document/type identity, actual enabled/visible/focus state, composition provenance, declared maxlength and a whole-selection boolean. It never returns the password, its length, or its hash. Known-inactive composition is required before focus or selection. The read-only native planner revalidates the owned X11 window generation, focus and held/latched input state; a fresh protected snapshot follows that potentially blocking check immediately before input. The whole-field selection is changed with `setSelectionRange`, not a value setter. Content is supplied through browser-native `Input.insertText`; empty replacement dispatches Backspace. Tabs and non-BMP text work without key-based focus traversal. LF, CR, NUL, surrogates, more than 64000 code points, and text exceeding the declared HTML UTF-16 maxlength are rejected before content input. A known initial maxlength violation is rejected before focus.

Success is only **dispatched**, with fixed explanatory metadata. It does not prove the contents or application acceptance. Same-field/type/focus/composition are checked afterward without plaintext readback. If an application changes its own masking while handling input, the result is uncertain, but the application may already have exposed or retained the value. There is no atomic prevention of application/human races or universal secrecy claim. Luda does not retain secret tool arguments in its operation history/report; an external client supplying arguments has its own logging policy.

## A rejected selection implementation and its fix

The first implementation used virtual CDP Ctrl+A to select the old password. Actual public MCP qualification found that Chromium 153 on this X11 stack published the **old password plaintext into PRIMARY**. CLIPBOARD was unchanged and the newly entered password was absent, but the old-value leak is a blocker, not a passing limitation. The candidate was not merged.

A separate ordinary-account, sandboxed Chromium probe compared virtual Ctrl+A, exact-node DOM `setSelectionRange`, and DOM `select`. Ctrl+A exported the old synthetic password; both DOM selection methods preserved a preseeded PRIMARY marker before and after native insertion. The shipped route uses `setSelectionRange` with same-call password/focus/composition checks. Full public MCP qualification independently verifies CLIPBOARD and PRIMARY preservation, plus absence of old/new synthetic passwords. No restoration is attempted, since restoring after publication would not undo disclosure.

The exact original probe, its content-free output, the failing public-MCP result and source fingerprint are retained under `tests/evidence/owned-secret/`. The probe uses only synthetic values and reports booleans/byte counts, never password bytes. It is test setup, not a second production input path.

## Actual qualification

Combined immutable run `run-1789897823673218346` passed all **18 owned-secret checks** in 19.851 seconds and the existing ordinary owned-browser suite in 16.686 seconds, with source unchanged and no tagged process survivors. This used Chromium 153.0.8010.12, Playwright 1.63.0, ordinary UID 1001, sandbox enabled, and a private Xvfb/D-Bus desktop. A subsequent bounded regression added explicit clipboard preservation across empty Backspace clearing: `run-1789897965306480080` passed **19/19** in 20.157 seconds, with source unchanged and no tagged survivors. Only public MCP tools supplied tested UI input. The synthetic app independently reports SHA256, decoy SHA256, submit/paste counters, focus/type and trusted composition metadata; it never sends password bytes to its oracle.

The checks include ordinary-operation refusal before and after entry; tab/non-BMP exact app hash; no paste or submission; both clipboard selections unchanged; a real paste-blocking password field followed by explicit native replacement; empty clearing; UTF-16 maxlength and LF/CR refusal before changing decoy focus; focus theft; replacement during selection; type and document changes; post-input app demasking reported uncertain; trusted native composition in another field preserved by pre-focus refusal; and secret-free status/report responses. The active-composition test runs last and closes the temporary session afterward. Earlier fixture attempts incorrectly assumed Escape or a reload shortcut proved composition termination; those failures are retained rather than converted into a cancellation claim.

Ten focused unit tests cover boundary ordering, invalid text/UTF-16 limits, post-selection replacement, post-input uncertainty, and strict rejection of malicious secret success packets containing text or extra progress. Together with ordinary browser, rich-editor and report regressions, 45 tests pass. A first fixture argument-name collision, an empty-selection replacement trigger, a repeated replacement callback that trapped keyboard traversal, and report/close-tool harness assumptions were corrected; no failing production behavior was hidden as a pass. The original PRIMARY leak and final successful matrix are retained separately.

Run the optional suite after explicitly installing the browser extra and test browser:

```sh
.venv/bin/python scripts/qualification_matrix.py --suites owned-secret \
  --executable /absolute/test-browser/chrome
```

This scopes AUTH-01/AUTH-07 to an owned password input and the tested provider. It does not qualify existing browser profiles, other engines, arbitrary masked custom controls, browser extensions, real accounts, or macOS/Silo. No requirement is marked release-qualified.
