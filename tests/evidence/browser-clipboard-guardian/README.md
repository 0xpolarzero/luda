# Browser clipboard input guardian review

The initial clipboard candidate (`005c61c`) called physical X11 `send_chord` from its browser worker. The browser guardian kills its descendants on parent EOF. This also kills the keyboard guardian before that guardian can release owned keys.

The original independent ordinary-UID private-Xvfb probe and output are retained in `original/`. It observed Control keycode 37 pressed, stopped the injector, closed the browser guardian's controller pipe, and independently observed keycode 37 still pressed after the browser guardian exited 0. The probe releases only its explicit test keys in `finally`; the display is disposable. No shared desktop was used.

`probe.py` is the portable version. It uses the real browser guardian, keyboard guardian, X11 injector and GTK fixture, with a **test-only browser worker** that calls `send_chord`. It tests this process-lifecycle composition, not a complete public-MCP clipboard edit. Run only in an ordinary-account, private Xvfb/D-Bus session with `LUDA_ISOLATED_TEST_DISPLAY=1`, using a Python environment containing Luda's dependencies. It prints before/after XQueryKeymap evidence. A retained held key demonstrates the unsafe composition; do not relabel that output as a passing cleanup test.

A replacement implementation using browser-local virtual key events must be qualified separately. This historical probe deliberately retains physical X11 input and therefore does not by itself validate that replacement. Browser-owned virtual keydown cancellation and actual clipboard/model effects need their own evidence.

## Replacement transport lifetime check

`virtual-probe.py` uses actual sandboxed Chromium and the existing `Worker.rich_key` CDP transport. A test-only worker pauses immediately after the real `Input.dispatchKeyEvent` keyDown returns, before keyUp. Closing its browser controller then exercises actual guardian EOF cleanup. The independent XQueryKeymap oracle sees no physical keys pressed either after virtual keyDown or after cleanup; the guardian exits 0 with cleanup proof `1`. `virtual-result.log` retains the original private UID1001 run.

Run with the same private-session requirements plus `LUDA_CHROMIUM_EXECUTABLE` pointing to an explicitly provisioned Chromium. This establishes the virtual transport's cancellation lifetime, not its integration into every clipboard call or correctness of rich-text edits. The candidate's actual MCP/model/clipboard suite supplies those separate checks. The original physical-guardian failure remains valid and unchanged.
