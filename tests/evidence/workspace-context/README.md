# Sampled active workspace as screenshot context

Private ordinary UID1001 Xvfb/XFWM/D-Bus run `1789903284541160950` passed in 2.419 seconds with unchanged source inventory, based on `0dcc8fa` plus this correction. The original single-driver explicit-switch cases still pass. Added actual two-driver and external-switch cases preserve the observing driver's snapshot cache, restore the same sticky GTK target focus, and assert the complete native window signature is unchanged. The old pointer target is nevertheless refused with `STALE_OBSERVATION`, effect none, because sampled active workspace differs. The independent fixture counter stays zero. Workspace is independently read with xprop and active XID with xdotool.

The same retained image remains accessible as a historical image-matching template; current-layout access refuses it. A new screenshot works. No human/shared desktop or credentials are used. This tests separate Desktop clients in one test process, not an additional paid agent evaluation. The external wmctrl request is issued only inside the private test desktop.

The native metadata decoder tests available workspace zero, absent optional count, unsupported EWMH, advertised-but-missing metadata, malformed type/format/count, excess payload and bounds. Capture-time context changes and historical-template behavior are also covered. The correction adds no polling daemon or shared history counter: external change-and-return occurring wholly between observations can still escape detection. Nothing in these results qualifies continuous tracking or every WM. The original explicit-switch regression is retained separately in `workspace-observation-gap`.

Reproduce with an ordinary account and writable artifacts directory:

```sh
.venv/bin/python scripts/qualification_matrix.py --suites workspace-snapshots
```

The matrix creates the private display/session. Gzip files retain the exact live assertions, log and source/environment inventory with zero mtime. Subsequent documentation and one additional decoder assertion were not part of that live run; runtime and fixture bytes were unchanged.
