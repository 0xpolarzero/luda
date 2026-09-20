# Electron fixture qualification

The opt-in `electron` suite uses a real, separately installed Electron binary. It never substitutes Chromium, downloads dependencies during a run, executes agent-generated JavaScript, or requires a model API. Luda drives the UI; the app's preload observes input/change/selection events and atomically writes an independent JSON oracle. The fixture loads only local HTML, denies hostname resolution, and uses a private profile. The runner creates an ordinary-user Xvfb/D-Bus session and cleans tagged descendants.

## Reproduction

The tested build is the [official Electron 44.4.3 release](https://github.com/electron/electron/releases/tag/v44.4.3), Linux arm64. Its `electron-v44.4.3-linux-arm64.zip` SHA256 is `61f084a5ac0f1835efc12b9db17042d92c8c617b03578f96a888acd4a05a0b10`, independently compared against the release's `SHASUMS256.txt` before extraction. This validates the published checksum, not a separate cryptographic release signature. Download and extract the archive in a test-only directory; preserve executable permissions. Other architectures need their own matching official archive/checksum.

Use the locked project environment and an ordinary account:

```sh
.venv/bin/python scripts/qualification_matrix.py --suites electron \
  --electron-executable /absolute/test-tools/electron-44.4.3/app/electron
```

`LUDA_ELECTRON_EXECUTABLE` is the equivalent environment variable. A missing executable is a failing `dependency_missing` result, including under `--all`. Chromium's separate `--executable` cannot satisfy Electron's dependency. This suite is optional setup, not a mandatory hosted CI download.

The local run used uid 1001, Electron 44.4.3, embedded Chromium 152.0.7977.130, Node 24.21.0, X11, `ACCESSIBILITY_ENABLED=1`, Electron `force-renderer-accessibility`, and test-only `--no-sandbox`. This does not qualify Electron's sandbox configuration. Exact arguments, component versions, source fingerprints, logs and case outcomes are saved under `artifacts/qualification-matrix`; suite artifacts also appear under `artifacts/electron`.

## Evidence and limits

The initial real run exposed two failures rather than qualifying Electron wholesale:

- Unicode single-line insertion and textarea LF, tab, emoji, combining text and trailing LF matched the app oracle exactly. Clearing that nonempty textarea failed: the provider reports one selection, but both its own and enclosing `Document.GetTextSelections` return no ranges. Legacy `Text.GetSelection` reports `(0,17)` while the app reports UTF-16 `(0,23)`, corresponding to code points `(0,20)`. Guessing an inverse of this lossy conversion would be unsafe. Luda now returns `SELECTION_UNVERIFIABLE` with an uncertain effect after selection changed, preserving the text and refusing subsequent deletion. A Document provider returning no ranges may use the legacy selection interface only when the entire field has no non-BMP characters, for which UTF-16 and code-point indices are identical. Exact BMP replacement and clearing are separately qualified.
- The checkbox advertises `check`/`uncheck`, while the original backend only accepted generic toggle/click/activate. Directional actions are now recognized and independently checked against the desired state. A true return without a state change remains uncertain. The live fixture verifies check and uncheck using app state.

Button activation increments an independent counter. Ordinary protected-field read/type are refused without changing the app's password length. Explicit secret entry is **unsupported** by this Electron provider, which lacks EditableText; a successful refusal test does not qualify secret delivery. Disabling renderer accessibility in a fresh process/profile produces `ACCESSIBILITY_UNAVAILABLE` in the tested build, with screenshot fallback advice; providers that retain native menus are accepted only if renderer controls are absent.

The final local regression run records 15 passing checks out of 16, with source unchanged and no tagged process survivors. It passes all cases except the required non-BMP empty replacement; the suite intentionally exits nonzero. Initial failure evidence remains in the earlier matrix run artifacts; subsequent runs never overwrite those directories. A failed required replacement case keeps the suite nonzero. This fixture does not qualify arbitrary third-party Electron apps, contenteditable rich text, remote Mac onboarding, Wayland, sandboxed renderer deployment, or asynchronous application validation.

## Explicit full-field GUI clear follow-up

The additional run `run-1789896020080360319` keeps the semantic `empty-replace-exact` failure intact and adds three **separate** public Desktop GUI assertions. With the existing non-BMP multiline content still present, it verifies field focus, dispatches Ctrl+A, independently observes DOM UTF-16 selection 0..23 while preserving the text and sibling entry, then dispatches Backspace. The resulting public accessible readback and independent DOM both contain empty text; the sibling entry remains byte-for-byte unchanged. The fixture's independent renderer oracle observes state only and supplies no input.

Both keyboard results remain `effect: dispatched` with `application_outcome_verified: false`. The subsequent readback establishes observed empty text; it does not make keyboard dispatch itself verified or prove native composition inactive (`composition.known:false`). This is deliberate input against a synthetic field with no active composition, not an automatic fallback after an uncertain mutation. The original refusal preserves text; the separately named workflow explicitly selects the whole field anew.

All three added checks pass. The complete suite is **18/19, exit 1**, because the original semantic replacement remains unsupported; it is not hidden or relabeled. Source was unchanged, the private ordinary-account run lasted 7.131 seconds, and the runner found no tagged survivors. Retained results and exact source fingerprints are in `tests/evidence/electron-native-clear/`. Existing test-only `--no-sandbox` scope remains unchanged.

This supplies an application-specific route for TXT-09 full-field empty replacement, whose acceptance does not prescribe `desktop_type`. It does **not** fix `desktop_type(mode='replace', text='')`, establish EDIT-03 arbitrary selected-range replacement, qualify Electron wholesale, or infer reliable non-BMP AX selection. No production code changed and no release qualification status changed.
