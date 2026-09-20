# Delayed recycled-row qualification

DATA-01 now has representative native evidence beyond a large in-memory table:
**10/10 checks passed** through existing public MCP observe/scroll/inspect/choose
operations. No new search API or production change was required.

The GTK3 fixture maintains exactly four ListStore rows and their native accessible
objects. A downward wheel request starts a 450 ms GLib timer, disables the view
while loading, then replaces those slots with the next page's records. Only the
current page exists in the model; the remaining records are not hidden accessible
rows. The app persists its own stable integer record IDs, loaded-page history,
selection events, loading/filter state and scroll-request count.

A separate bounded read-only AT-SPI observer established actual object reuse:
`Record 001` became `Record 005` at the same provider `:1.2` and object path
`/org/a11y/atspi/accessible/17` in the recorded session. It supplies no input.
The public old handle then returned `STALE_TARGET`, effect `none`, without selecting
a row. Reinspection and choosing the explicitly visible `Record 005` selected
app ID 5; another delayed page and fresh inspection selected app ID 9.

Both later pages have two rows whose label is literally `Duplicate`. The workflow
does not treat that label or a row index as a record identifier: it reacquires the
separate visible Record identity cell. Changing the filter replaces the same slots
with records 100–103; the old handle is refused and freshly observed Record 102
selects app ID 102. A visible “End of data” label plus unchanged page contents is
distinct from the stalled-loader case. Two deliberate scrolls with unchanged
contents stop the test's bounded search as **no progress**, never “item absent.”

## Scope and limits

This is a real GTK3/XFWM application driven through public MCP, with private
ordinary-account Xvfb/D-Bus/XDG state. It models asynchronous recycling through a
local timer; it is not a production remote data service or network-failure test.
The script knows the requested visible record labels and uses app state to await
and independently verify effects. It is not a fresh-model usability evaluation.

Provider connection/path/name validation is not durable business identity. If a
provider reuses the same path and all exposed meaning for a different hidden
record, Luda cannot infer that hidden change. The duplicate-label test therefore
uses explicit visible identity cells, not stale same-label handles. A page that
provides no distinguishable identity may require application-specific context or
human clarification. The test does not claim atomic loading/selection or general
absence proof from no progress. No catalog priority or release-qualification
status changed.

The prior P1 audit's missing representative evidence is now addressed for this
fixture. Existing bounded scroll/reinspect primitives suffice here; there is no
observed navigation blockage justifying a generic search-through-virtualization
helper.

## Evidence and reproduction

Final immutable run `run-1789898977732665480` took 10.247 seconds with source hash
`a44c1b7535fe6952b410f441d1266f6178fa8ffd81c4062aca35fd91b5f1c86f`;
source was unchanged and the runner found no tagged survivors. The initial
nine-check run passed in 10.070 seconds; the second run added direct provider-path
proof. Neither run failed, and both original matrix reports are retained in
[tests/evidence/recycled-rows](../tests/evidence/recycled-rows/README.md).

On a provisioned ordinary account:

```sh
uv sync --locked --no-default-groups
.venv/bin/python scripts/qualification_matrix.py --suites recycled-rows
```

The registered runner provisions only private session state, not packages. Usual
GTK3/AT-SPI/Xvfb/XFWM qualification dependencies are required. All tested input uses
public tools; the independent observer and app oracle do not mutate the desktop.
