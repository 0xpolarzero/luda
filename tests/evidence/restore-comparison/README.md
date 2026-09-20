# Restore comparison evidence

The final ordinary-UID1001 run passed seven grouped checks; results.json retains exact outputs and environment.json the unchanged runtime/source fingerprint. It used private Xvfb, D-Bus, HOME and XDG paths; all apps and XFWM were owned and explicitly terminated/reaped. No shared desktop application was driven.

Earlier attempts chained external unmaximize/move immediately after changing the same fixture's minimum-size hints. XFWM kept that fixture maximized, so the independent external-move precondition failed. initial-hints-followup-failure.json preserves its actual maximized state and the correctly unknown comparison. The first attempt also lacked isolated HOME/XDG despite a private display/bus; it is not counted as isolated-session qualification. The retained final run creates all private paths before starting the bus and WM. The external-move case now starts a separate owned fixture; it does not replay a failed action against the previous window.

Historical comparison cannot detect external changes that revert between observations. Exact current same-generation rectangles are compared; no geometry is forced. See ../../live_restore_comparison.py for the self-contained runner and ../../../docs/WINDOW-GEOMETRY-QUALIFICATION.md for scope.
