# Scope, contracts and architecture

## Product definition

A local agent should operate the same visible desktop that the Linux user sees, inside the same Linux environment guest, without a vendor account, separate model loop, second VM, or cloud desktop. The interface must make intended targets and observed effects explicit. Linux owns VM lifecycle and viewer delivery; this package owns desktop control and agent instructions.

The current implementation is a working experimental prototype for Ubuntu 24.04/XFCE/X11, developed on ARM64 with KasmVNC. Its name and version do not imply production support. The 346-case acceptance catalog defines the broader target; it is not a list of implemented or passed cases.

## Own code versus upstream primitives

We own the MCP schemas, target validation, coordinate mapping, session launcher, action/result contract, text policy, worker isolation, tests and skill. We reuse maintained primitives: the official Python MCP SDK, Xlib, AT-SPI/GObject introspection, isolated XKB/XTest helpers for keyboard and pointer input, xdotool/wmctrl for window control, xclip for clipboard ownership, scrot for image capture and wmctrl/xprop for window metadata. There is no AIO/Cua worker, remote API, proprietary runtime or model inside this package.

This does not make us independent of Linux toolkit bugs. An application can expose broken accessibility or transform pasted content. A correct driver must report limits and uncertainty rather than conceal those behaviors.

## Process architecture

```text
Codex MCP client (inside guest remote execution context)
  └─ luda-session --user desktop -- luda
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

MCP errors use `isError=true`. Validation performed by the SDK can use the SDK's own error format. Unknown errors must not claim no effect. No automatic retry of mutations occurs. MCP cancellation requests stop bounded worker processes and trigger input cleanup. Status remains responsive while cleanup finishes; incomplete cleanup quarantines new operations. Client-side timeout alone does not necessarily cancel a request. Request-id deduplication and atomic compound application transactions are not provided.

## Identity and observations

Windows are identified by XID, process ID, Linux process start time and a shared random X-resource property. The property survives remapping and changes on destruction/recreation, including reuse of the same XID by the same live process. This is a stale-resource check, not a trust boundary against malicious X11 clients.

Screenshot IDs belong to one server, expire after 15 seconds and hold native/image dimensions, RandR topology and window-layout/focus metadata. Native capture is bounded to 32 million pixels; both returned dimensions are bounded to 2,560 pixels. Corrupt captures fail explicitly; a valid black image remains a valid observation. Pointer coordinates use returned image pixels. The driver rejects layout/focus/resolution changes and changes to the full RandR topology and points outside the active client or an explicitly owned observed popup. A root-surface hit test rejects covered targets. These checks do not atomically exclude subsequent human input or detect every content change. Layout validation is not proof that a control under the pixel is unchanged.

Client geometry is queried through Xlib root-coordinate translation. Frame extents come from the window manager; no hard-coded title-bar adjustment. Accessibility top-levels must uniquely match either client or frame geometry. GTK4 providers with unavailable screen coordinates can use exact window title and dimensions only when that identifies one top-level within the process; unreliable element bounds are omitted. Ambiguous mapping is a capability failure, not permission to target every window in a process.

Element IDs are opaque, server-local and expire after 60 seconds. The worker resolves the original top-level and object path, revalidates process identity, role, displayed name and a private bounded full-name fingerprint, and requires enabled/showing state for mutation. Widget reuse with identical identity properties remains a limitation. Trees are bounded and partial coverage is declared. Caches are bounded to 16 screenshots and 4,000 handles.

## Text contract

`desktop_type` inserts at the code-point caret/replaces a selection by default; `mode="replace"` replaces the entire field. Native EditableText is preferred. Where only editable Text is exposed, the driver verifies focus and selection, pastes, and compares exact destination readback. An uncertain native mutation never triggers clipboard fallback. Browser hypertext and toolkit differences require provider-specific qualification; unsupported or mismatched readback is not success.

`desktop_paste` is the deliberate lower-level clipboard operation. It selects a common application shortcut from WM_CLASS, permits an explicit override, and samples exact clipboard bytes/ownership before dispatch. It does not verify destination text. Neither operation adds a submit key.

LF, Tab, blank lines, leading/trailing whitespace, Unicode and trailing newlines are not normalized or trimmed. Other C0 controls, DEL, NUL and CR are rejected before clipboard/app mutation. The limit is 1 MB UTF-8. CRLF support would need an explicit option, not silent conversion. Unpaired Unicode surrogates are invalid text and must be rejected by validation.

Application transformation is possible: single-line fields, formatting, clipboard managers, terminal line discipline and IMEs can change the effect. `verified` is only appropriate for actual exact readback. Raw paste remains a primitive; verified typing must report an error when it cannot establish exact destination text.

CLIPBOARD is overwritten. PRIMARY is unchanged. The owned clipboard process lives until replaced or server exit; automatic restoration is deliberately not implemented because early restoration can corrupt asynchronous paste or overwrite a newer human copy. Shift+Insert can read PRIMARY. Terminal pasted newlines can execute commands; the tool does not automatically accept paste confirmation dialogs.

`desktop_type_secret` explicitly replaces an observed protected EditableText field or a scoped owned-browser password input ([contract](OWNED-BROWSER-SECRET.md)). It never reads the value, uses no clipboard, redacts provider exceptions and reports dispatched only. Ordinary reads/typing/selection refuse protected fields. The MCP client still supplies the tool argument; Luda cannot control client-side transcript retention. Screenshots reflect application masking. Submission remains separate.

## Timing, concurrency and recovery

AT-SPI runs in disposable subprocesses so a hung provider cannot indefinitely block the server. Input commands have bounded subprocess deadlines. A timed-out mutation is uncertain. Drag attempts mouse-button release in `finally`, including cooperative cancellation; cleanup commands have their own bounded deadline. An independent inherited-pipe companion attempts held-mouse release after controller death; a private-X-server test independently observed release after SIGKILL. It cannot guarantee cleanup if the companion or X server is also killed. Xlib operations run in disposable helpers, so X-server death does not terminate the MCP server.

Locks serialize cooperating server instances for the same Unix user/display. They do not lock out human viewer input, other programs or privileged processes. Focus can change between a check and an X11 event. Cooperative admission is FIFO with bounded waiting and no mutation replay. A shared `desktop_control` pause file blocks cooperating clients before and during mutations; observations and status remain available. This is cooperative takeover, not exclusive hardware ownership.

`desktop_wait` polls bounded text/window/fresh-element conditions and sampled pixel stability without retrying input. Pixel stability is not application completion. Metadata helpers reconnect after X-server restart; old window generations no longer resolve. `desktop_reconnect` explicitly selects a validated same-account XFCE session and invalidates prior handles while preserving pause state. It does not restart application accessibility bridges that fail to reconnect. `desktop_recover_input` retries only owned cleanup, never interrupted input; unresolved cleanup keeps admission blocked. Doctor reports available screensaver/login1 lock hints without activating or unlocking a service, plus advisory fixed-sample font coverage. Unknown lock state is not proof of an unlocked desktop. Broader lock/unlock and clean host onboarding evidence remain incomplete.

## Source references

The implementation uses the installed MCP SDK's v1.30 interface (pinned), not an assumed latest API. Reference: [official Python MCP SDK](https://github.com/modelcontextprotocol/python-sdk/tree/v1.30.0). Accessibility contract: [AT-SPI documentation](https://gnome.pages.gitlab.gnome.org/at-spi2-core/libatspi/). X11 primitives: [xdotool](https://github.com/jordansissel/xdotool), [xclip](https://github.com/astrand/xclip).
