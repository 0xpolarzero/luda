# Accessibility bus generation

Unique provider connection names are unique within one D-Bus server lifetime.
They can recur after a server restart. Process lifetime, window identity, provider
name, object path, role and accessible-name fingerprints therefore do not alone
identify a handle across accessibility-bus replacement.

## Reproduced boundary

The explicit provider fixture in `tests/bus_generation_fixture.py` keeps a real
GTK window and the same process alive, reconnects its own Gio AT-SPI provider,
and reuses the provider name and accessible paths after private bus replacement.
This is a deliberately implemented provider reconnect policy, not ordinary GTK
bridge behavior. The independent application counter measures actual activation.

Before the fix, the same PID/start, provider `:1.2`, root `/fixture/window` and
button `/fixture/button` accepted an old handle after the private bus restarted.
The old handle dispatched an action and the counter incremented. The socket path
was reused while the authenticated GUID changed. The pre-fix probe remains in
ignored `artifacts/bus-generation/before-fix-probe.log`.

The ordinary GTK bridge still did not automatically reconnect. Forcing its cleanup
and initialization preserved the window but left stale inaccessible root objects;
that separate unsuccessful probe is retained in `gtk-reinit-limitation.log`.
Luda does not restart user applications or attempt that bridge reinitialization.

## Guard and ownership

Each inspected private handle now carries `root_bus_guid` as well as its provider
connection name. Mutation/read resolution checks it before traversal and again
immediately before operating on the resolved target. A changed or missing handle
GUID returns `STALE_TARGET` with no mutation. Missing, disconnected or malformed
current connection identity returns `ACCESSIBILITY_UNAVAILABLE` without input.
Both private fields are removed from public inspection responses.

The worker calls the exported C `atspi_get_a11y_bus`, which GI does not expose,
then reads `dbus_connection_get_server_id` from that exact connection. It does not
open another bus connection or launch another process. The GUID getter reads the
authenticated connection metadata; initial libatspi connection establishment stays
inside the existing bounded disposable-worker watchdog. Its allocated GUID string
is freed with `dbus_free`. The libatspi connection is neither closed nor unreferenced:
the [2.52 implementation](https://github.com/GNOME/at-spi2-core/blob/AT_SPI2_CORE_2_52_0/atspi/atspi-misc.c)
returns its cached connection without adding a reference.

The [D-Bus connection API](https://dbus.freedesktop.org/doc/api/html/group__DBusConnection.html)
distinguishes this authenticated server-address GUID from the bus-wide GetId.
Different transports to the same bus can have different GUIDs. Refusing a handle
when the connection endpoint changes is conservative and intentional; there is no
separate discovery/GetId connection that could refer to another bus during a race.
The [AT-SPI API](https://docs.gtk.org/atspi2/func.get_a11y_bus.html) confirms the
function is unavailable to language bindings; the narrow ctypes bridge uses
explicit C argument/return types rather than reading GI object memory.

This does not make multiple provider calls atomic. Bus loss during an operation
can still produce an uncertain result, and same-provider, same-name/path reuse
within one generation remains indistinguishable. Reinspect after lifecycle changes.

## Qualification

`tests/test_bus_generation.py` exercises missing/disconnected connections, malformed
GUIDs, native string cleanup, sanitized library failures, missing/changed handle
generations and a generation change during target resolution. The private-cache
regression verifies public redaction. **510 unit tests passed** at this revision.

The opt-in matrix suite `bus-generation` runs as an ordinary user on private
Xvfb/D-Bus/XDG state. The live run passed all five assertions in 1.502 seconds:
initial real action, same live target on a new bus, private metadata redaction,
old-handle refusal without counter change, and fresh-handle activation. The normal
GTK semantic suite also passed in 6.189 seconds. Both runs had unchanged source
fingerprints and no surviving owned processes. Evidence is retained in
`artifacts/qualification-matrix/run-1789871863583900006/` in the qualification
worktree. This qualifies the explicit provider lifecycle guard, not every toolkit's
ability to recover its own accessibility bridge.
