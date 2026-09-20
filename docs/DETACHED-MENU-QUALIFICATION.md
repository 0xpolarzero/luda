# Native detached-menu qualification

MENU-08 requires “Tear-off or detached menu: new identity and coordinate context.”
Existing nested-menu and overlay fixtures already cover other menu transitions;
this test specifically exercises a native GTK3 `Gtk.TearoffMenuItem` and its
separate managed window. It is a representative toolkit fixture, not evidence
that every application, tray or menu implementation supports detachment.

`tests/live_detached_menu.py` drives the real stdio MCP server. Its only
application setup is launching `tests/detached_menu_fixture.py`; every interaction
uses existing public desktop tools. The fixture independently persists native
tear-off state, intended/wrong action counters and an exact UTF-8 proof file.

The workflow:

1. Inspect the owner, invoke its observed menu button and observe the owned
   override-redirect menu outside the owner client rectangle.
2. Click the native dashed tear-off row visible in the retained screenshot.
   This pinned fixture uses the observed menu's `image_bounds`, center X and a
   screenshot Y offset of eight pixels. That row assumption is explicit and is
   not a general theme/scale-independent menu selector.
3. Identify the new managed menu window by its own public window identity. The
   former attached popup has a different XID. Reusing its old snapshot is refused
   with `STALE_OBSERVATION`, without either action counter changing.
4. Activate and move the detached window with public window tools, observe its
   new image context, inspect its own menu items, and click the intended item's
   position mapped from its new native bounds into that screenshot. Verify the
   exact proof file and intended counter; the wrong-action counter stays zero.
5. Close the detached window, wait for its absence and native reattachment, then
   verify the former detached element handle is `STALE_TARGET`. Reinspect the
   owner and deliberately reopen the attached menu, with no extra action.

With GTK 3.24.41 on the ordinary UID 1001 private Xvfb/D-Bus/XFWM desktop, **all seven checks passed
in two complete runs**, taking 4.568 and 4.817 seconds. Both runs used unchanged
source fingerprint
`d70e837c837e876fefc02b6202c35a74a9edbf2a905835e68e391e240e413f4e` and left no owned
process survivors. Their retained evidence is under
`artifacts/qualification-matrix/run-1789873608220658547/` and
`run-1789873630199032932/` in the qualification worktree. Earlier bounded probes
that stopped before implementing the complete workflow remain recorded as
incomplete/nonzero; they are not counted as full-workflow passes.

GTK3 exposed usable AT-SPI frame/menu/item bounds for the detached window in this
fixture, so no provider limitation was encountered on that path. The initial
tear-off row was selected from its actual screenshot. This does not establish a
universal detached-menu discovery strategy, GTK4/Qt support, system-tray support,
other themes, or a fresh-agent usability pass. No runtime API, catalog acceptance,
priority or qualification status changed.

Run the opt-in suite as the ordinary desktop user:

```sh
.venv/bin/python scripts/qualification_matrix.py --suites detached-menu
```

The matrix owns the private display, D-Bus, window manager and XDG environment.
The suite saves synthetic screenshots, observation metadata, detached AX tree,
independent model state and case results under `artifacts/detached-menu/`.
