# Accessibility and desktop session lifecycle qualification

`tests/live_accessibility_lifecycle.py` starts two private Xvfb/D-Bus/XFCE sessions as the actual desktop user. It invokes the real `luda-session --session-pid` launcher, edits a GTK3 fixture with an independent persisted-buffer oracle, terminates only the private accessibility service and its child bus, and exercises the surviving application and a new provider. It never restarts the shared desktop, session bus, or user applications. Cleanup identifies private child processes by a unique inherited token and the same UID.

Run with the project environment and system GTK3, XFCE, Xvfb, wmctrl and gdbus installed:

```sh
.venv/bin/luda-session -- .venv/bin/python tests/live_accessibility_lifecycle.py
```

The 2026-09-20 isolated run recorded 16 successful assertions out of 18. The suite deliberately exits nonzero for unqualified behavior; results are written to ignored `artifacts/accessibility-lifecycle/`.

| Case | Evidence |
| --- | --- |
| Discover and launch against each real private XFCE session | Passed for both sessions, including the actual launcher subprocess environment. |
| Reject terminated session and discover a replacement | Passed; replacement had a different session PID and D-Bus address. |
| Restart the actual accessibility bus | Passed; the private service's new address differed. |
| Existing GTK3 application's accessibility bridge reconnects | **Failed:** no provider appeared within eight seconds; inspect returned `ACCESSIBILITY_UNAVAILABLE`. |
| Existing application's X11 fallback after accessibility loss | Passed; screenshot coordinates, pointer, selection and clipboard paste produced the exact independent buffer. |
| Same Desktop discovers a newly launched application after bus replacement | Passed; exact semantic text replacement verified independently. |
| Old window handle after fixture closure | This worktree returned `BACKEND_ERROR` instead of expected `STALE_TARGET` when the X11 client list became empty. Main has a separate empty-client-list fix; integrated rerun is required. |

`ACCESSIBILITY_UNAVAILABLE` means no accessible window can be scoped to the target. Multiple candidates or incomplete uniqueness enumeration still return `AMBIGUOUS_ACCESSIBILITY_WINDOW`; missing element handles still return `STALE_TARGET`. These distinctions do not establish whether an application lacks accessibility support or temporarily lost its bridge.

The disposable worker discovers a fresh accessibility bus for each request, which suffices for new providers. It cannot make an already running GTK application reconnect its own lost accessibility bridge. Do not automatically restart applications: that risks unsaved work. Screenshot controls remain a tested fallback in this fixture.

The launcher can discover a new complete desktop session, but an already running stdio server retains its original environment. These tests do **not** qualify automatic in-process reconnection of that server to a replacement session. Reattachment needs an explicit session transition that validates the new same-UID session, replaces the backend environment, and invalidates old handles without replaying uncertain operations.
