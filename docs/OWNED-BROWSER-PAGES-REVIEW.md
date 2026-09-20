# Extra owned pages: observation preserved, semantic scope unchanged

The concrete usability bug was broader than a missing multi-tab DOM provider:
`Desktop.inspect` asked the optional owned provider first, so its scope refusal
prevented otherwise available native accessibility inspection. A second tab
blocked the original native window's entire inspection. A separate popup also
blocked inspection of the opener, although native popup inspection worked.

The narrow fix catches only `BROWSER_SCOPE_UNSUPPORTED` while inspecting and
continues independently bound native AT-SPI inspection. A successful result has
native `nodes`, `text_fields: []`, and:

```json
{"owned_browser": {"available": false, "code": "BROWSER_SCOPE_UNSUPPORTED"}}
```

This does not create an empty successful result if native accessibility fails.
Cancellation, deadlines, stale identity and all other provider failures propagate.
Cached owned element IDs retain their original provider and still refuse the
unsupported scope. There is no mutation fallback, new page binding, automatic
switch, navigation, approval or credential reuse. Once the extra page closes,
ordinary owned-field discovery works again. Existing tool description/generated
tool docs explain this distinction; no skill change was needed.

## Actual private diagnostic and regression

A sandboxed Chromium 153.0.8010.12/Playwright1.63.0 session opened two owned local
HTTP origins on different loopback ports. Native controls explicitly opened a tab,
closed it, opened a popup, completed a synthetic callback, closed it and returned
to the opener. Both native windows deliberately had `Same Title`; selection used
the newly observed window identity, not title alone. App-written counters/origins
were independent HTTP oracles, with no DOM/CDP test input or real account.

The original baseline retained:

- Second-tab original-window inspect: `BROWSER_SCOPE_UNSUPPORTED`, effect `none`.
- Cached owned read during two tabs: the same explicit refusal.
- Popup opener inspect: the same refusal, while popup native AX remained usable.
- Native popup completion incremented child and opener counters once, with no
  field inputs. Closing it restored the opener's visible “Returned from child.”

The first setup attempt stopped on `ACTION_REQUIRED`: Chromium advertised both
`press` and `showContextMenu`, so the fixture needed the exact observed `press`
action. That original failure is retained. The completed baseline diagnostic
records the unsupported responses unchanged; its successful process exit meant
“diagnostic completed,” not multi-page owned support.

The fixed run `run-1789899872468005031` recorded eight observations with explicit
regression assertions in 9.029 seconds. Its source fingerprint was
`50ba062374e2388ae7d998744ebdb058a594bafe62e05f02caef6e5ad6af1db2`, unchanged
throughout, with no tagged survivors. Both original-window inspections now returned
native nodes and explicit owned-unavailable metadata. Cached owned read still
refused; close/recovery and the native callback workflow passed. Four focused
fallback contracts plus 12 owned-browser and 10 secret tests passed. No catalog
priority or release qualification status changed.

[Evidence](../tests/evidence/owned-pages-baseline/README.md) preserves initial,
baseline and fixed reports/responses. Reproduce as an ordinary provisioned account:

```sh
.venv/bin/python scripts/qualification_matrix.py --suites owned-pages-probe \
  --executable /absolute/path/to/provisioned/chromium
```

## Origin visibility and the next boundary

After deliberate Ctrl+L, the popup's native address field read
`127.0.0.1:<port>/child`, omitting the scheme. That observation distinguishes the
fixture's ports but is **not exact serialized origin evidence**. The independent
app oracle knows its complete local origin; this is not information the production
tool inferred from the displayed address. The test does not exercise a same-title
third-party decoy, real OAuth state/nonce validation, cookies/account identity,
redirect chains or browser-extension approval.

A future bounded extension could enumerate opaque owned page IDs, opener IDs,
current document IDs and browser-observed serialized origins without URLs' paths,
queries or fragments. Titles would remain untrusted context; an origin would not
attest account, expected identity provider or successful OAuth. Non-HTTP/inherited
or opaque origins must be represented explicitly, not guessed from URL prefixes.
New-page discovery itself must not select or approve anything.

Do not equate CDP `Browser.WindowID` with an X11 XID: its documented type is a
browser window identifier, and `getWindowForTarget` returns that identifier plus
bounds, not an advertised native-X11 mapping. Geometry/title coincidence is not
an exact identity bridge. Explicit page activation would require separately
validated active native-window generation plus live page/document/focus binding,
with ambiguous associations refused and the final race stated honestly. That is
larger than the proven inspection fix and is not implemented here.

Primary references: [Chromium Browser protocol](https://chromedevtools.github.io/devtools-protocol/tot/Browser/)
for target/window identifiers; [Playwright Page](https://playwright.dev/python/docs/api/class-page)
for page instances and explicit `bring_to_front`; [Location.origin](https://developer.mozilla.org/en-US/docs/Web/API/Location/origin)
for origin serialization. None establishes OAuth identity attestation.
