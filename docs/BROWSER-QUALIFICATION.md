# Offline browser qualification

`tests/live_browser.py` exercises real stdio MCP calls against headed Chromium. Playwright launches the browser, prepares synthetic offline content and reads independent DOM/file outcomes. Luda performs the tested focus, selection, text entry, dialog dismissal, file-chooser interaction and window targeting. No external websites or accounts are used.

Run it inside a dedicated Xvfb/XFWM4/session-D-Bus environment, or hold `/tmp/luda-live-tests.lock` for the entire run when using the existing `:1` desktop:

```sh
.venv/bin/python tests/live_browser.py --browser /absolute/path/to/chrome
```

Artifacts are written to `artifacts/browser/`: version/environment and case outcomes, the initial accessibility tree, native chooser accessibility response, and a chooser screenshot. A nonzero exit means a required assertion failed; unsupported semantic text entry is not silently counted as success because its clipboard fallback worked.

## Baseline on Chromium 153.0.8010.12

- Exact clipboard replacement passed for textarea and contenteditable, preserving multiline text, tabs, emoji, combining marks and trailing newlines.
- Semantic selection followed by clipboard insertion replaced the four-codepoint `👩🏽‍💻` sequence correctly in both fields. The independent DOM values matched the expected surrounding text.
- Readonly and disabled controls rejected semantic mutation and retained their values.
- JavaScript alert acknowledgment with Return and confirm dismissal with Escape passed, verified by DOM changes. Playwright observed dialogs but did not accept/dismiss them.
- A native file chooser opened. Screenshot-targeted Open selected the Unicode filename and the browser received its exact synthetic file contents.
- Input targeting the inactive second window was refused without changing it. Activating that window and pasting produced exact content.
- **Four semantic typing assertions failed on the baseline:** Chromium exposes Text and editable state but no EditableText interface for these fields. `desktop_type` returned `UNSUPPORTED` or `NOT_EDITABLE`. The separate clipboard tests passed. This is a capability gap, not proof of working semantic typing.

## Environment and workflow findings

`--force-renderer-accessibility` alone did not register Chromium on AT-SPI in the fresh isolated session. The fixture also sets `ACCESSIBILITY_ENABLED=1`. Chromium's own [AT-SPI fuzzer uses that environment override](https://chromium.googlesource.com/chromium/src/+/9360d08502357e2ea00f4f052bb6a8ca9277e27a/chrome/test/fuzzing/atspi_in_process_fuzzer.cc). Desktop accessibility readiness does not prove every application has enabled its bridge.

The native GTK file chooser could not be uniquely mapped through Luda accessibility in this run. The retained screenshot supports the pinned-layout Open-button coordinates used by the fixture. This is a specific screenshot workflow, not general file-dialog layout coverage. Return while the location field was focused closed this chooser with a DOM `cancel` event; explicitly clicking Open generated `change` and selected the expected file. Window disappearance alone would have produced a false success claim.

Firefox is not installed and has not been qualified. Browser versions, rendering backends, zoom, IME behavior, cross-origin frames, complex editors and alternate native chooser layouts need additional evidence. The fixture documents its assumptions rather than claiming all browser interactions are covered.

## Verified typing fallback and adversarial application behavior

The post-baseline suite also tests empty replacement, collapsed carets before/after astral characters and at field end, rejected paste events, delayed application updates, transformed input and focus theft to another editable widget. Each scenario starts from fresh synthetic DOM state. An uncertain error is never retried as a clipboard action; the independent clipboard cases reinitialize their own state.

In the first fallback run, textarea multiline, empty replacement, all three collapsed carets, delayed completion, rejected/transformed-paste error classification and the focus-theft negative case passed. Unicode selection readback and contenteditable hypertext exposed further provider discrepancies despite correct DOM effects; those failures remain explicit until corrected and rerun.

`.github/workflows/browser.yml` provisions the pinned Playwright browser in a dedicated setup step and passes its executable to the test. The test itself performs no browser downloads. CI uses a fresh isolated Xvfb display and a 180-second suite watchdog. A configured workflow is not evidence of a hosted CI pass; inspect the uploaded versioned result artifact.
