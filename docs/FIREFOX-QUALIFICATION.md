# Firefox Linux ARM64 qualification

Real Mozilla Firefox **156.0**, ordinary UID 1001, private Xvfb/D-Bus/XFWM, disposable profile and XDG directories, 2026-09-20. No Firefox runtime dependency or global browser installation was added. Mozilla's [release metadata](https://product-details.mozilla.org/1.0/firefox_versions.json) reported stable 156.0, released 2026-09-15. The official [ARM64 en-US archive](https://archive.mozilla.org/pub/firefox/releases/156.0/linux-aarch64/en-US/firefox-156.0.tar.xz) matched [upstream SHA256SUMS](https://archive.mozilla.org/pub/firefox/releases/156.0/SHA256SUMS):

```
7dd9425eafa0decf61c0f6bc56dc71cba84595495dc01395d3eea38a18aaf710
```

The tested launcher SHA256 was `bb63da37df3ed6b95ceec748916487587890f8e20863b6f75f39e43aa7a96c1c`. The complete archive was checked before extraction, not only the small launcher. `scripts/provision_firefox.py` reproduces provisioning to a new external directory, verifies the pinned upstream entry and streamed archive hash, and refuses existing destinations or mismatched archives.

## Method and results

`tests/live_firefox.py` drives the actual public Luda MCP methods. A local HTML page publishes its own DOM state to a loopback HTTP/file oracle every 80 ms; no WebDriver, remote debugger, or injected DOM mutation driver performs actions. Password evidence contains only an exact-match boolean and length. All input is synthetic. The fixture owns its browser and window-manager process groups and uses a disposable profile with the first-run notice suppressed. HTTP/HTTPS proxy preferences direct non-loopback requests to an unavailable local port; this is not a claim of OS-level network isolation.

The final run recorded **14 of 15 checks passed**, with source hash `2a72e625b304c657c1b9772d689f85c1b6954c7d7d6b0432523765818b4a99d3` unchanged before/after. The suite **exits nonzero** because explicit protected input remains unsupported. Related requirements are WEB-02, EDIT-01/02/03/09, SEM-04, AX-09; this small fixture does not qualify those requirements across all applications.

| Case | Result |
|---|---|
| Scoped Firefox accessibility discovery | Passed |
| Public code-point selection across emoji/skin tone/ZWJ | Passed; DOM UTF-16 endpoints independently checked |
| Replace selected emoji with Japanese text | Exact DOM value and caret passed |
| Multiline replacement with LF, tab, Japanese, astral text, combining mark, two trailing LF | Exact DOM value and AT-SPI readback passed |
| Empty replacement | Passed |
| Checkbox and button | Passed against independent DOM state |
| Ordinary protected read and typing | Refused with `PROTECTED_FIELD` |
| Explicit protected input | **Unsupported**; no keyboard/clipboard secret fallback |
| Deliberate clipboard multiline paste | Exact independent DOM value passed; tool correctly reports dispatched |
| Insert astral into initially ASCII text | Exact value and public caret passed |
| Genuine U+FEFF before text and immediately after astral text | Preserved exactly; selection replacement and caret passed |

Local artifacts are in `artifacts/firefox`: original setup runs, baseline results, focus/caret diagnostic runs, final `edge-run.log`, `results.json`, tree, browser log and passive oracle. The first two attempts encountered Firefox's first-run notice; the initial harness also attempted to find the intentionally redacted password by its original name. Those failures remain in the saved logs. The first functional baseline exposed real offset, native editing and checkbox failures; subsequent runs changed explicit implementation or fixture preconditions, rather than selecting a favorable repeat.

## Provider behavior and bounded corrections

Firefox's [release-pinned DOMtoATK implementation](https://github.com/mozilla-firefox/firefox/blob/FIREFOX_156_0_RELEASE/accessible/atk/DOMtoATK.h) adds one U+FEFF after each non-BMP character so ATK offsets align with DOM UTF-16 offsets. [Mozilla bug 1346535](https://bugzilla.mozilla.org/show_bug.cgi?id=1346535) documents that convention. Luda identifies the reported Gecko toolkit, validates the full bounded readback count and padding pattern, removes exactly each synthetic padding character, and converts caret/selection offsets to the public code-point contract. Genuine U+FEFF survives. Unknown/inconsistent conventions are refused rather than globally stripping invisible characters.

The [release-pinned EditableText callbacks](https://github.com/mozilla-firefox/firefox/blob/FIREFOX_156_0_RELEASE/accessible/atk/nsMaiInterfaceEditableText.cpp) return without editing text roles despite advertising EditableText. This was independently observed: accepted native requests left both ordinary and password DOM values unchanged. Inspect keeps the actual provider interfaces and adds `native_text_mutation_supported=false` for Gecko text controls. Ordinary `desktop_type` uses the existing focus/selection/clipboard/readback transaction. Direct native set/insert and explicit secret input refuse before dispatch. Generic providers that fail after mutation still report uncertainty; they are not silently retried.

A correct ATK range alone was insufficient for Gecko insertion: selecting the emoji showed the expected DOM range but subsequent paste inserted at the old editor caret after deleting that range. Focusing first did not fix it. A separately verified collapsed caret at the requested start, followed by the requested range, fixed the actual DOM result. Luda now performs that bounded Gecko-specific selection preparation and refuses if the caret cannot be verified. Original failing evidence is retained.

No claim is made for Firefox rich contenteditable, password fallback, pending IME composition, extensions, all ARIA widgets, browser dialogs, or subsequent Firefox versions.

## Reproduce

Provision outside the source tree (Python 3.12 or newer):

```sh
python3 scripts/provision_firefox.py --directory /absolute/new/firefox-test-directory
```

Then run as an ordinary desktop UID, with a writable `artifacts/firefox` directory and a worktree-local venv:

```sh
LUDA_ISOLATED_TEST_DISPLAY=1 xvfb-run -a -s '-screen 0 1440x1000x24 -nolisten tcp' \
  dbus-run-session -- .venv/bin/python tests/live_firefox.py \
  --executable /absolute/new/firefox-test-directory/firefox/firefox
```

The fixture starts XFWM itself; do not start a second window manager. A nonzero exit currently preserves the unsupported protected-input capability.
