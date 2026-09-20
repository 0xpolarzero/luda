# Opt-in GTK3 composition observer: prototype stopping point

A startup GTK3 module can observe composition activity in stock Mousepad without reading preedit text. It cannot establish exact field ownership or complete initial context state through the public signals tested here. This is a **read-only research fixture**, not a production IME guard. EDIT-10 remains unqualified; no Luda input behavior, installer, module setting or default application environment changed.

The test module uses public `GtkIMContext` emission hooks and weak references. Context generations are monotonically assigned on first observed signal, never inferred from pointer reuse; they are **observed-object generations, not proof of creation or field identity**. Destruction removes that object's activity. Start/end establish observed context activity; a first changed signal establishes neither. An observed active context can conservatively establish process activity. Zero observed active contexts remains unknown, including at startup. No preedit getter, text export, accessible name, focus-to-context heuristic or private GTK struct is used.

Public [emission hooks](https://docs.gtk.org/gobject/func.signal_add_emission_hook.html) require signals without `G_SIGNAL_NO_HOOKS`; the module checks each signal and hook result. [GTK3_MODULES](https://docs.gtk.org/gtk3/running.html) supports an explicit absolute module path for GTK3-only application startup. That is not a documented context-creation notification or an enumeration of existing contexts. The tested `GtkIMContext` public properties are `input-purpose` and `input-hints`; neither identifies an owning widget. Start and end signal arguments contain the context instance, not the field. Observing a current focused widget or X11 window would not repair that missing ownership relation.

## Actual evidence

Ubuntu ARM64, GTK 3.24.41, Mousepad 0.6.1, ordinary UID 1001, private Xvfb/D-Bus and new HOME/XDG directories. Only the owned target receives the module environment. Test input uses xdotool in that private display: this qualifies the hook prototype, not public Luda mutation behavior.

- Startup Entry: actual `Ctrl+Shift+U`, `306b` produced real preedit, independently observed by the fixture's widget signal. Escape ended it without changing the committed empty buffer. The module observed **two context streams for one field**, so context count must not be presented as field count.
- Late Entry attachment: the independent widget oracle already had nonempty pending preedit. Module attachment reported unknown; no start event was replayed. Only subsequent events became visible.
- Controlled signal cases: a first `preedit-changed` stays unknown; start followed by changed stays active without inspecting text (including an empty preedit representation). End changes the observed context to inactive. Destroying another active context without end removes its activity, and later objects receive different generations. These are explicitly synthetic lifecycle contracts, not claims that every installed input engine emits all such sequences.
- Stock Mousepad: per-process startup loading observed real built-in Unicode composition start/change/end. The retained screenshot visibly shows underlined `u306b` after `BASE`; the owned file remained exactly `BASE`. The two context streams again do not prove field binding. Screenshot review corroborates visible composition, not a universal engine contract.

Final probe assertions pass for all three scenes: startup 24 events / four observed generations; late 12 events / four generations; Mousepad 19 events. [Raw evidence](../tests/evidence/gtk3-ime-module/final/results.json), source hashes, content-free events and the deliberately captured synthetic screenshot are retained. Attempt 1 contains the original Entry-only proof. Attempt 2 retains a failed test assumption that the context had no properties; the actual two non-identity properties were recorded, then the assertion was corrected. Attempt 3 passed before a final cleanup/lifecycle assertion refinement. No original run was overwritten.

## Reproduce and limits

Requires existing GCC, GTK3 development headers, system Python GI, Mousepad, xdotool, Xvfb and D-Bus. No downloads or global installation occur. As an ordinary account, with a writable existing parent directory:

```sh
/usr/bin/python3 scripts/probe_gtk3_ime_module.py --output /absolute/new-owned-output
```

The output directory must not exist. Each private scene has a 15-second outer bound and owns its process group; the stock app is terminated explicitly. The module's file descriptor is a fixture-owned local event log. It is not a production IPC service, bounded long-running monitor, authenticated provider or globally loaded library. The fixture retains synthetic screenshots only when explicitly run. It does not demonstrate every engine, GTK4, Qt, provider reconnect, privileged application support or race-free input.

**Stop here rather than integrate a partial guard.** A production path still needs authoritative lifecycle from context creation and exact app-controlled field/context identity, or an explicitly cooperating app implementation. No public exact stock-widget association was found in this bounded test. A process-wide active refusal could be conservative, but reporting inactive or authorizing a specific field from this observer would exceed the evidence. Even a correct snapshot does not prevent composition starting between observation and external input; atomic protection needs application-side checking at the mutation boundary. See the earlier [native feasibility audit](NATIVE-IME-FEASIBILITY.md).
