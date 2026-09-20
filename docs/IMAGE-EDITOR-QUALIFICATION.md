# Native image editor qualification

`tests/live_image_editor.py` qualifies **APPS-09/APPS-10** against actual GIMP **2.10.36**, Ubuntu package **2.10.36-3ubuntu0.24.04.1**, on arm64 X11. GIMP is an optional test dependency installed from official Ubuntu apt repositories; it is not a Luda runtime dependency.

The test runs as ordinary desktop UID 1001 in its own 1200×900 Xvfb, D-Bus session, XFWM and private XDG/GIMP configuration. It creates a synthetic 640×480 PNG and opens it in a fresh GIMP instance. All interaction uses one persistent public stdio MCP connection. No GIMP scripting, plug-in automation, hidden application state or direct X input drives the test. Pillow authors the input fixture and independently reads the exported file; screenshot pixels locate the visible canvas.

This installed GTK2 GIMP reports `ACCESSIBILITY_UNAVAILABLE` for its window. The test explicitly checks this condition, then uses screenshots, observed window identities and pointer/keyboard tools. It demonstrates the screenshot-only workflow rather than pretending the canvas has semantic elements.

## Verified effects

- A pencil drag produces a black stroke through three independent image coordinates.
- A rectangle-selection drag followed by explicit foreground fill changes all 9,600 pixels in the intended 120×80 region.
- Two deliberate zoom-in keys and three downward wheel ticks move the visible filled rectangle upward by 96 screenshot pixels. Both before/after rectangles retain their 160-pixel rendered height.
- Actual Export Image and PNG options dialogs create a new PNG. The oracle waits for successful image decoding, not merely file existence, without repeating any GUI input.
- The exported image remains 640×480. Its 26,969 changed pixels are black and all lie inside the stroke/selection regions. Every pixel outside those regions, including the colored alignment rails, remains unchanged. The original input file hash remains unchanged.

Tool dispatch responses are not the application oracle. Screenshots establish scroll effects and independently decoded exported pixels establish editing/export effects.

## Reproduce

Install the optional distro test application with `apt-get install --no-install-recommends gimp`. Other requirements are the ordinary live-test Xvfb, dbus-run-session and xfwm4 packages, plus the project's locked Python environment. No download occurs during the test.

Run from a writable checkout as the ordinary desktop account:

```sh
.venv/bin/python tests/live_image_editor.py
```

For a root-owned development checkout, prepare a writable artifact parent and use the existing desktop account:

```sh
mkdir -p artifacts/image-editor
chown silo-desktop:silo-desktop artifacts/image-editor
runuser -u silo-desktop -- .venv/bin/python tests/live_image_editor.py
```

Each default run preserves a separate `artifacts/image-editor/run-*/` directory with screenshots, tool transcript, source/export images, GIMP log and result metadata. `LUDA_IMAGE_ARTIFACTS` can select an explicit new directory. The outer process group has a 100-second limit and only its private session is cleaned up. It does not use or modify the shared desktop.

## Development probes and limits

Raw development artifacts retain the first failures instead of presenting an uninterrupted first attempt:

- `attempt-1`: the initial probe expected accessibility; actual GTK2 registration was unavailable. The test now explicitly qualifies screenshot fallback.
- `attempt-3`: the canvas locator assumed a fully visible rail edge; GIMP's dashed image border occludes its outer pixels. The fixed-theme locator now accounts for that observed border.
- `attempt-6`: the PNG path existed before GIMP finished writing it. A premature decoder read failed. The oracle now polls for a decodable file within eight seconds; input is never retried.
- `attempt-7`: all five grouped checks passed. The final source was rerun in `final/` and passed the same five checks after adding unique default artifact directories and screenshot-space dialog bounds. Attempts 2, 4 and 5 were intermediate observation probes, not full qualification passes.

This is one established image editor, fixed theme/geometry and a small editing workflow. It does not qualify all GIMP features, arbitrary themes, pen pressure, color management, layers, filters, animations, other export formats or Wayland. Dialog coordinates are derived from observed bounds with fixed-version button offsets. The suite intentionally fails if the expected no-accessibility condition changes, requiring the evidence claim to be revisited.

The deliberate tool and fill shortcuts follow the [GIMP 2.10 tool reference](https://docs.gimp.org/2.10/en/key-reference-tools.html), [edit reference](https://docs.gimp.org/2.10/en/key-reference-edit.html) and [zoom reference](https://docs.gimp.org/2.10/en/gimp-view-zoom.html).
