# Explicit GUI routes for two GTK4 semantic limits

`tests/live_gtk4_gui.py` demonstrates two useful user workflows through existing public screenshot, keyboard and clipboard tools. It **does not repair or relabel GTK4 semantic checkbox/selection support**. The original [toolkit qualification failures](TOOLKIT-QUALIFICATION.md) remain separate evidence.

The test reuses the actual `gtk4_fixture.py` widgets, without direct application setters to perform the fallback actions. It runs as ordinary UID 1001 with private Xvfb, D-Bus, XFWM and XDG state. All interaction uses one persistent public stdio MCP connection. Actual `Gtk.CheckButton` and `Gtk.TextBuffer` state is independently saved by the fixture. Tested distro GTK is **4.14.5+ds-0ubuntu0.10**, arm64.

## Checkbox: semantic refusal, explicit observed click

The current `desktop_set_checked(checked=true)` result is `UNSUPPORTED_ACTION`, effect `none`: no recognized semantic state-changing action is available. The independent widget remains unchecked. This response and state are retained, not counted as successful semantic support.

A fresh screenshot locates the visible checkbox in the observed window. One `desktop_click` checks it; the actual widget becomes checked, the checkbox screenshot changes visibly, and fresh public inspection exposes the `checked` state. A separately intended click on a new screenshot unchecks it, verified by the widget and another screenshot.

For this route, inspect the current desired state first; a click is a toggle, not an idempotent set operation. Reobserve afterward. The fixture uses the observed 620×480 client bounds and a fixed-theme checkbox offset, never GTK4's unavailable accessibility coordinates.

## Selected-text replacement: preserve the uncertain failure first

Supported full-field `desktop_type` prepares `prefix SUFFIX`. The semantic `desktop_select(7,13)` call then returns **`ACCESSIBILITY_ERROR`, effect `uncertain`**. The fixture reports identical before/after state in this run: text `prefix SUFFIX`, caret 13, no selection, editor not focused. This observed lack of change is not a general promise about uncertain provider failures.

The explicit GUI sequence starts from a new screenshot and focuses the editor with a click, then sends Ctrl+End and Ctrl+Shift+Left. The actual GTK buffer reports selection `[7,13]`, caret 7; the screenshot visibly highlights only `SUFFIX`. `desktop_paste` replaces that selected word with `日本語 👩🏽‍💻` followed by LF and a tab. The independent final buffer and public `desktop_read_text` both report exactly `prefix 日本語 👩🏽‍💻\n\t`, 17 Unicode code points, caret 17 and no selection. The final screenshot shows the preserved prefix and replacement on the intended lines.

Clipboard dispatch alone is not destination verification. The independent buffer and public readback establish the result here. Ctrl+Shift+Left is qualified for this known final ASCII word, not arbitrary locale-sensitive word boundaries, grapheme ranges or RTL selections.

## Evidence and reproduction

The first complete run passed **five GUI assertions**, while retaining both semantic limitation responses separately. Raw evidence under `artifacts/gtk4-gui/attempt-1/` includes public tool results, before/after widget state, inspection and screenshots of the unchecked/checked checkbox, selected suffix and final text. No tagged processes survived cleanup. Source fingerprints remained unchanged at `a81db82afb8fdc12499f6579ff112874394c1f311ff37cc654d11eff9f8e987c` before this report was added.

The earlier diagnostic probes are preserved: `probe-1` stopped because the harness expected the older generic `UNSUPPORTED` label instead of the actual `UNSUPPORTED_ACTION`; `probe-2` only captured the initial screenshot and had no completed workflow assertions. Neither is represented as a passing full run.

Run in a writable checkout as the ordinary desktop account:

```sh
.venv/bin/python tests/live_gtk4_gui.py
```

The script creates its private display itself, uses a unique artifact directory by default and has a 50-second outer watchdog. A root-owned checkout needs an ordinary-user-writable `artifacts/gtk4-gui` parent. Dependencies are the project's locked Python environment and existing GTK4/AT-SPI/Xvfb/XFWM test packages; the test downloads nothing.

This is an application-specific, explicit route chosen after observing a provider limitation, not an automatic runtime fallback or a universal GTK4 support claim. The semantic errors remain errors, no retry is hidden, and no new runtime API or fixture backdoor was added.
