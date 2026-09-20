# IME composition: explicit unsupported capability

`desktop_doctor.ime_composition` reports `state: unknown`, with detection, explicit commit/cancel, and conflicting-input guards unsupported. Normal text tools still operate, but an exact match verifies the exposed text at that moment; it does not establish that no pending composition exists. No input-method state is reset, no daemon is started, and no Escape or Return is sent to infer state.

Acceptance case **EDIT-10 remains unqualified and blocked** for the generic X11/AT-SPI backend. This is separate from the browser rich-text representation blocker; neither issue is solved by ordinary Unicode paste passing.

## Real application probes

`tests/live_ime.py` uses real GTK3 Entry and TextView controls. Their own `preedit-changed` signals and persisted buffers provide the independent oracle. `tests/live_ime_browser.py` uses actual Chromium and records DOM composition/input events independently. Both start composition by sending real X11 Ctrl+Shift+U and the digits `306b` through public Luda input methods, leaving `u306b` uncommitted. Neither test synthesizes a composition event or uses CDP to insert composition.

The probes start their own XFWM4 on a private Xvfb/session bus and set `GTK_IM_MODULE=simple` only in their private environment. No IBus or Fcitx daemon is needed for this real composition. Absence of those processes therefore cannot prove that composition is inactive.

The 2026-09-20 local evidence covers 18 scenarios, each with a fresh field and an independent active-composition oracle:

| Operation while `u306b` is pending | GTK Entry | GTK TextView | Chromium textarea |
| --- | --- | --- | --- |
| Read | Returns committed `BASE`; preserves preedit | Returns committed `BASE`; preserves preedit | Returns `BASEu306b`, including pending preedit; preserves composition |
| Focus same field | Clears pending preedit; focus returns verified | Preserves preedit | Preserves composition |
| Replace with `AGENT` | Clears preedit; returns verified for `AGENT` | Returns verified for `AGENT`, while preedit remains; later explicit Return yields `AGENTに` | Clipboard path commits pending `に` instead of requested text; returns `TEXT_MISMATCH`, uncertain |
| Insert `AGENT` | Clears preedit; returns verified for `BASEAGENT` | Returns verified for `BASEAGENT`, while preedit remains; later Return yields `BASEAGENTに` | Clipboard path commits pending `に`; returns `TEXT_MISMATCH`, uncertain |
| Select existing text | Clears preedit | Clears preedit | Selection verifies; composition remains active |
| Paste `AGENT` | Shortcut commits pending `に`; payload does not arrive | Shortcut commits pending `に`; payload does not arrive | Shortcut commits pending `に`; payload does not arrive |

Raw paste accurately reports dispatch and clipboard ownership rather than exact destination text. Its effect can still conflict with a pending composition. GTK exact-text success is not a claim about future state: in TextView, later explicit completion changes the document. In Entry, the more serious issue is cancellation of text the user had not committed. The probe's final Return is an explicit fixture-owned oracle step, never a proposed production recovery action.

GTK's observed accessible states, object attributes, text attributes and text do not identify the pending preedit. Chromium exposes preedit in the ordinary text value without a reliable composition marker in the existing Luda interface. Searching for underlines, the letter `u`, candidate windows, the active engine, or language/locale would confuse ordinary text with composition and miss other cases.

The probes deliberately exit nonzero until conflicting-input handling qualifies. Their ignored artifacts retain per-case responses, synthetic preedit events, independent text, and read-only AX evidence. These tests do not qualify IBus/Fcitx engines, every language, every input method, GTK4, or Qt.

Run separately:

```sh
LUDA_ISOLATED_TEST_DISPLAY=1 xvfb-run -a \
  -s '-screen 0 1200x800x24 -nolisten tcp' \
  dbus-run-session -- .venv/bin/python tests/live_ime.py

LUDA_ISOLATED_TEST_DISPLAY=1 xvfb-run -a \
  -s '-screen 0 1200x800x24 -nolisten tcp' \
  dbus-run-session -- .venv/bin/python tests/live_ime_browser.py
```

The browser fixture uses the documented local Chromium test binary and blocks hostname resolution. Tested native packages: GTK 3.24.41, AT-SPI 2.52.0, XFWM4 4.18.0 on ARM64 Ubuntu. The observed input is synthetic fixture data only.

## Why an engine query is insufficient

GTK provides [`IMContext.get_preedit_string`](https://docs.gtk.org/gtk3/method.IMContext.get_preedit_string.html) for an application's own input context. [`Entry::preedit-changed`](https://docs.gtk.org/gtk3/signal.Entry.preedit-changed.html) and [`TextView::preedit-changed`](https://docs.gtk.org/gtk3/signal.TextView.preedit-changed.html) explicitly distinguish text awaiting commitment from the buffer. These are in-process interfaces, not an external AT-SPI composition query. [`IMContext.reset`](https://docs.gtk.org/gtk3/method.IMContext.reset.html) can clear preedit, so using it as a probe is destructive.

IBus exposes current input contexts and engines, plus preedit-change signals. The [`InputContext` public interface](https://ibus.github.io/docs/ibus-1.5/IBusInputContext.html) and [current service introspection](https://github.com/ibus/ibus/blob/main/bus/inputcontext.c) do not provide a generic read-only current-preedit snapshot getter. Observing future signals does not reconstruct a composition already active when a client attaches, and cannot cover GTK's separate built-in context. IBus also allows engines to choose clear or commit behavior on focus loss through [`update_preedit_text_with_mode`](https://ibus.github.io/docs/ibus-1.5/IBusEngine.html); global focus changes are not neutral probes.

Fcitx's documented [D-Bus controller](https://fcitx-im.org/wiki/DBus_Interface) reports the selected input method and activation state. Its [controller implementation](https://github.com/fcitx/fcitx5/blob/master/src/modules/dbus/dbusmodule.cpp) does not turn those into a snapshot of the focused application's pending composition. Deactivate, toggle, and reset are mutations. No Fcitx engine was live-qualified in this task.

Chromium internally has `HasCompositionText`, composition-range and confirm/clear operations on its [`TextInputClient`](https://chromium.googlesource.com/chromium/src/+/HEAD/ui/base/ime/text_input_client.h). These belong to Chromium's internal text-input client. The [DevTools Input domain](https://chromedevtools.github.io/devtools-protocol/tot/Input/) offers composition-setting operations, which mutate the document; it does not make an external GTK/AT-SPI-only backend aware of composition in every application. DOM composition events helped the test oracle because it was installed before composition began. A listener attached afterward must not assume inactive state.

## Reliable scope for future implementation

A supported composition adapter needs an authoritative **current** state tied to the exact application, document and focused field; event-only history with an unknown start is insufficient. It must return `unknown` on attach gaps, navigation, focus identity changes, provider loss and restart. Preserve only activity/range/generation metadata where possible; do not retain private preedit text in logs.

For cooperating applications, an in-process GTK input-context adapter or a browser integration established before editing can supply state. Mutation must revalidate the same composition generation immediately before input; a detected active composition should refuse conflicting input without changing focus or selection. Explicit commit/cancel needs its own user-intended action and independent postcondition, not a generic key assumed to mean the same thing in all apps. A complete solution also needs prevention or detection of human-input races between the check and mutation.

No application injection or new plugin is implemented here. Until that scoped contract is supported, the skill instructs agents to preserve visible or suspected composition and have it explicitly completed or cancelled before conflicting operations. This limitation is reported openly instead of claiming that every ordinary field is safe or making all normal typing unavailable.
