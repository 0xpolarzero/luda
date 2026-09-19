# Scope, contracts and architecture

## Product definition

A local agent should operate the same visible desktop that the Silo user sees, inside the same microsandbox guest, without a vendor account, separate model loop, second VM, or cloud desktop. The interface must make intended targets and observed effects explicit. Silo owns VM lifecycle and viewer delivery; this package owns desktop control and agent instructions.

The current implementation is a working experimental prototype for Ubuntu 24.04/XFCE/X11, developed on ARM64 with KasmVNC. Its name and version do not imply production support. The 345-case acceptance catalog defines the broader target; it is not a list of implemented or passed cases.

## Own code versus upstream primitives

We own the MCP schemas, target validation, coordinate mapping, session launcher, action/result contract, text policy, worker isolation, tests and skill. We reuse maintained primitives: the official Python MCP SDK, Xlib, AT-SPI/GObject introspection, xdotool for intentional input events, xclip for clipboard ownership, scrot for image capture and wmctrl/xprop for window metadata. There is no AIO/Cua worker, remote API, proprietary runtime or model inside this package.

This does not make us independent of Linux toolkit bugs. An application can expose broken accessibility or transform pasted content. A correct driver must report limits and uncertainty rather than conceal those behaviors.

## Process architecture

```text
Codex MCP client (inside guest remote execution context)
  └─ luda-session --user silo-desktop -- silo-desktop
       ├─ discovers one explicit user's XFCE session
       ├─ drops to that ordinary user
       └─ stdio MCP server
            ├─ per-display, cross-process advisory lock
            ├─ X11 window identities + geometry + screenshots
            ├─ clipboard owner (one managed child)
            └─ short-lived AT-SPI workers (5-second hard deadline)
```

The launcher does not guess DISPLAY, choose an arbitrary user's D-Bus, modify the global Xauthority policy, or escalate privileges. It fails on ambiguous sessions. The root invocation is an attachment mechanism; control runs as the desktop account. There is no HTTP listener.

## Outcome contract

Every normal response includes `ok` and elapsed time. Mutations also report an effect:

- `none`: input was not dispatched (or a documented no-op).
- `dispatched`: the backend sent input/accepted an action; application outcome remains unverified.
- `verified`: a specifically named condition was observed, such as exact editable-text readback or active window identity.
- `uncertain`: input might have taken effect; inspect before retrying.

MCP errors use `isError=true`. Validation performed by the SDK can use the SDK's own error format. Unknown errors must not claim no effect. No automatic retry of mutations occurs. Request-id deduplication, comprehensive cancellation and transactional compound actions remain backlog items.

## Identity and observations

Windows are identified by XID + process ID + Linux process start time. This catches process reuse, not every possible XID reuse within one live process; generation tracking remains a release blocker.

Screenshot IDs belong to one server, expire after 15 seconds and hold native/image dimensions and window-layout/focus metadata. Pointer coordinates use returned image pixels. The driver rejects layout/focus/resolution changes and points outside the active client's bounds. It does not detect all content changes or unmanaged overlay interception. Layout validation is not proof that a control under the pixel is unchanged.

Client geometry is queried through Xlib root-coordinate translation. Frame extents come from the window manager; no hard-coded title-bar adjustment. Accessibility top-levels must uniquely match either client or frame geometry. Ambiguous mapping is a capability failure, not permission to target every window in a process.

Element IDs are opaque, server-local and expire after 60 seconds. The worker resolves the original top-level and object path, revalidates process identity/name/role, and requires enabled/showing state for mutation. Widget reuse with identical identity properties remains a limitation. Trees are bounded and partial coverage is declared. Caches are bounded to 16 screenshots and 4,000 handles.

## Text contract

`set_text` means complete replacement of one accessible editable text element. It requires readable text and compares exact readback. `enter_text` means clipboard insertion at the current caret using an explicit application shortcut. It verifies CLIPBOARD bytes but not destination text. Neither operation intentionally adds a submit key.

LF, Tab, blank lines, leading/trailing whitespace, Unicode and trailing newlines are not normalized or trimmed. Other C0 controls, DEL, NUL and CR are rejected before clipboard/app mutation. The limit is 1 MB UTF-8. CRLF support would need an explicit option, not silent conversion. Unpaired Unicode surrogates are invalid text and must be rejected by validation.

Application transformation is possible: single-line fields, formatting, clipboard managers, terminal line discipline and IMEs can change the effect. `verified` is only appropriate for actual exact readback. Current paste is a primitive, not a universal verified insertion implementation.

CLIPBOARD is overwritten. PRIMARY is unchanged. The owned clipboard process lives until replaced or server exit; automatic restoration is deliberately not implemented because early restoration can corrupt asynchronous paste or overwrite a newer human copy. Shift+Insert can read PRIMARY. Terminal pasted newlines can execute commands; the tool does not automatically accept paste confirmation dialogs.

Protected fields are unsupported for semantic read/write in this prototype. Screenshots reflect the application's own masking. A full credential-input feature needs a separate carefully specified contract; it cannot be inferred from ordinary text tests.

## Timing, concurrency and recovery

AT-SPI runs in disposable subprocesses so a hung provider cannot indefinitely block the server. Input commands have bounded subprocess deadlines. A timed-out mutation is uncertain. Drag attempts mouse-button release in `finally`, but process death, disconnect and cancellation need further qualification.

Locks serialize cooperating server instances for the same Unix user/display. They do not lock out human viewer input, other programs or privileged processes. Focus can change between a check and an X11 event. Human takeover and stronger input ownership remain release requirements.

There is no generalized condition-wait API yet. Callers observe/read back after dispatch. Full-desktop reconnect after X-server death, lock-screen handling and live backend hot-reload are not implemented.

## Source references

The implementation uses the installed MCP SDK's v1.30 interface (pinned), not an assumed latest API. Reference: [official Python MCP SDK](https://github.com/modelcontextprotocol/python-sdk/tree/v1.30.0). Accessibility contract: [AT-SPI documentation](https://gnome.pages.gitlab.gnome.org/at-spi2-core/libatspi/). X11 primitives: [xdotool](https://github.com/jordansissel/xdotool), [xclip](https://github.com/astrand/xclip). Silo's [desktop implementation](https://github.com/0xpolarzero/silo/blob/main/docs/SiloUI-DESKTOP.md) remains unchanged.
