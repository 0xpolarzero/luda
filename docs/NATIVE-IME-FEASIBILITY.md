# Native composition state: feasibility audit

Generic native EDIT-10 remains blocked. This audit found no authoritative external preedit-state channel in the installed GTK3/GTK4 AT-SPI stack. No production input behavior changed. The existing `composition: {known: false, active: null}` contract remains accurate.

## Actual read-only observations

On Ubuntu 24.04 ARM64, GTK 3.24.41 and 4.14.5, AT-SPI 2.52, an ordinary-user private Xvfb/D-Bus fixture opened Entry and TextView controls for each GTK version. Public Luda keyboard input established real `gtk-im-context-simple` preedit (`Ctrl+Shift+U`, then `306b`). An app-owned listener installed before editing independently recorded nonempty preedit and the committed buffer. Once composition was pending, the probe performed only accessibility reads: no focus, selection, reset, commit or cancellation.

All four controls retained pending composition and committed `BASE`. Their states, object/text attributes, text, interfaces and live D-Bus interface descriptions were unchanged from the inactive baseline. A second in-process listener attached after the input had quiesced received no replay, so its state remained unknown. This demonstrates an attach gap even for cooperating code that merely subscribes to future widget signals.

Final run `1789900684931593002` used source fingerprint `4b99c9148bfb4317e1e2ad7fdb35da9859c2920dc6463949a48a944c689633b2`. All four observation cases completed with unchanged source and no surviving owned processes. Exit zero means the observation probe completed; it does **not** qualify conflicting input. The first run attached its late listener while digits were still arriving; that timing mistake and both subsequent runs are retained under `tests/evidence/native-ime-state`. No original result was replaced.

Run the optional probe as an ordinary desktop user:

```sh
.venv/bin/python scripts/qualification_matrix.py --suites ime-state-audit --timeout 90
```

It requires GTK3/GTK4 GI packages and the matrix's normal private X11 dependencies. It does not require Chromium, IBus or Fcitx. These four cases do not qualify other engines, Qt, every locale, or future toolkit versions.

## Why the available interfaces do not solve it

GTK's public [`IMContext.get_preedit_string`](https://docs.gtk.org/gtk4/method.IMContext.get_preedit_string.html) and [preedit-start](https://docs.gtk.org/gtk4/signal.IMContext.preedit-start.html)/[preedit-end](https://docs.gtk.org/gtk4/signal.IMContext.preedit-end.html) interfaces belong to an application's own input context. Installed stock Entry/TextView controls do not expose a public getter for that private context. A text getter is not by itself a lifecycle guarantee; an empty string must not automatically mean every input method is inactive.

GTK4 [`Editable.get_delegate`](https://docs.gtk.org/gtk4/method.Editable.get_delegate.html) lets an Entry owner reach its Gtk.Text delegate and subscribe to [`preedit-changed`](https://docs.gtk.org/gtk4/signal.Text.preedit-changed.html). It does not recover past lifecycle events. Reset and key-filter methods are mutations, not observational alternatives. The [AT-SPI Text interface](https://gnome.pages.gitlab.gnome.org/at-spi2-core/devel-docs/doc-org.a11y.atspi.Text.html) and the actual exported interfaces in this probe provide no composition-state getter.

Exact field binding also needs care. GTK3's public [`Atk.Object.set_accessible_id`](https://docs.gtk.org/atk/method.Object.set_accessible_id.html) exported the fixture's non-user-facing field key through AT-SPI in both controls. In installed GTK4, both controls returned an empty AccessibleId. This matches the pinned [GTK 4.14.5 exporter](https://github.com/GNOME/gtk/blob/4.14.5/gtk/a11y/gtkatspicontext.c#L717), which returns an empty string for that property. Names, geometry and reused child indices are not equivalent identity proof. Newer in-process APIs do not retroactively provide an external channel in this installed stack.

## Smallest plausible cooperating contract — design only

A practical narrow adapter would be explicitly supplied by an application that owns its input context. It would observe lifecycle from before the first input, on the same UI thread, and expose only `known`, `active`, a composition generation, and field/context generations; preedit plaintext need not leave the application. Missing history, context replacement or lost provider identity would produce unknown, never inactive.

The adapter endpoint would bind to the same UID and process start, accessibility bus generation, provider unique name and object path, plus an app-controlled exact field key and generation. GTK3's demonstrated accessible ID is one possible key mechanism. GTK4 stock widgets in the installed exporter need additional public toolkit/application integration to establish this binding; no name/bounds heuristic is proposed. A custom accessible implementation is possible in principle but was not implemented or qualified here.

A registered provider reporting active or unknown would refuse conflicting operations before focus, selection or input. It would never send Escape/Return as a probe. Even a correct current-state snapshot does not make later X11 input atomic: human input can begin composition between check and dispatch. Strong prevention requires a cooperating application-side guarded operation that checks the expected field and composition generations at the mutation boundary. That is a separate, explicitly scoped input integration, not something an external monitor alone can promise.

This is not a recommendation to inject code into existing applications, preload a library globally, or blanket-disable normal text tools. There is no implemented native adapter in this change. Existing [IME limitations and destructive-conflict evidence](IME-COMPOSITION.md) remain in force.
