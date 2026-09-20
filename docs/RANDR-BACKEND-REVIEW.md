# RandR ABI and backend qualification

The independent review of `b241c1c` found no ABI mismatch or allocation-cleanup defect. `test_randr_native.py` compares the size and every field offset of all five ctypes structures against a compiled program including the installed public `Xrandr.h`. This passed on Linux arm64 with libXrandr 1.5.2. The ABI test explicitly skips if optional compiler/development headers are absent; runtime installation does not require either. Six additional tests cover successful cleanup, oversized arrays, disappearing CRTCs, failed transform retrieval that nevertheless allocated memory, malformed monitor arrays, and an unavailable extension.

Run those tests with:

```sh
.venv/bin/python -m unittest discover -s tests -p test_randr_native.py -v
```

`tests/live_randr_backends.py` starts and destroys only its own ordinary-user displays, choosing free display numbers. Luda reads metadata; `xrandr` independently configures these test displays. It needs Xvfb, KasmVNC for the `kasm` case, and optional `xserver-xorg-core` plus `xserver-xorg-video-dummy` for the `dummy` case. The no-extension semantic fixture additionally uses GTK3, XFWM and a private D-Bus/XDG session. No shared desktop configuration is changed. KasmVNC listens only on a private mode-0600 Unix socket, with TCP disabled and a fixed loopback public-IP setting that avoids STUN discovery.

```sh
.venv/bin/python tests/live_randr_backends.py
# Or explicitly choose installed test backends:
.venv/bin/python tests/live_randr_backends.py --backends xvfb no-randr
```

The actual results from Xvfb 21.1.12, KasmVNC 1.5.0 and Xorg 21.1.12 with dummy driver 0.4.0 were:

| Probe | Xvfb | KasmVNC | Xorg dummy |
| --- | --- | --- | --- |
| RandR metadata | Readable, version 1.6 | Readable, version 1.6 | Readable, version 1.6 |
| Two real CRTCs; swap positions with unchanged root size | Not qualified | Not qualified | Detected; independently checked with xrandr |
| Left rotation | Driver refused | Driver refused | Driver refused |
| 0.75 affine scale transform | RRSetCrtcTransform BadValue | RRSetCrtcTransform BadValue | RRSetCrtcTransform BadValue |
| Extended 1400×800 panning | Exceeds the fixed test framebuffer | BadRRCrtc | Applied and detected |

These refusals are recorded as driver limitations, not successful rotation/transform qualifications. The probe does not infer that every possible panning configuration is unavailable on Xvfb. Some failed xrandr operations disable an output before returning an error; Luda's metadata detects that changed state. The harness restores its owned baseline mode before the next independent capability probe.

A separate Xvfb started with `-extension RANDR` proves the extension is absent using `xdpyinfo`. Both native topology and `Desktop.observe` explicitly return `TOPOLOGY_UNAVAILABLE`. After that refused observation, semantic inspection and exact GTK text replacement still work, checked by the passive app's independent file oracle. Thus missing topology blocks screenshot-target validation without silently disabling all semantic tools.

Artifacts under `artifacts/randr-backends` include server logs, commands, package versions, complete sampled metadata, failure diagnostics, source fingerprints and owned-process cleanup. Successful metadata reads do not qualify hardware hotplug atomicity, physical monitor rendering, arbitrary mixed DPI, rotation, nonidentity transforms, VNC client multi-screen negotiation, or other CPU ABIs. Existing `live_geometry.py` independently checks that a logical-monitor change invalidates screenshot targets.
