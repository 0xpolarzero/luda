# Screenshot and native coordinates

`desktop_observe` returns `image_bounds` on every window and owned popup. These are clipped rectangles of **integer pixels in the returned screenshot**, ready to use with that response's `snapshot_id` and pointer tools. Existing `bounds` and `frame_bounds` remain native X11 root coordinates. Window `image_bounds` maps the client area, not its frame decorations.

The response declares the distinction explicitly:

```json
{
  "coordinate_spaces": {
    "bounds": "native_x11_root_pixels",
    "frame_bounds": "native_x11_root_pixels",
    "image_bounds": "returned_image_pixels",
    "pointer": "returned_image_pixels"
  }
}
```

For an integer center inside a non-null rectangle, use `x + width // 2` and `y + height // 2`. Edges are half-open: the first column/row is included; `x + width` and `y + height` are excluded. Fractional coordinates are still accepted by pointer tools, but the rectangle's exact guarantee concerns integer pixel positions. In particular, adding `0.5` to the only pixel of a narrow rectangle can move outside the corresponding native control.

`image_bounds: null` means no integer screenshot pixel maps into the native rectangle. This includes fully off-screen rectangles, zero-sized rectangles, and very narrow visible native regions skipped by downsampling. A non-null rectangle describes geometry, not visibility: another window can cover it, or its window may be minimized or on another workspace. Existing focus, layout, popup ownership and hit-testing checks remain in force. Observe again after moving or activating a window.

`desktop_inspect` has no screenshot association. It reports `bounds_coordinate_space: native_x11_root_pixels` for usable node bounds. GTK4's title/size fallback instead reports `unavailable` and continues to omit unreliable node coordinates. Inspect does not fabricate `image_bounds` or bind itself to an arbitrary cached screenshot.

## Exact rounding

The pointer mapping for an integer image column `i` is `floor(i * native_width / image_width)`. For a native client interval `[left, right)`, the corresponding integer image interval is therefore:

```text
[ceil(left * image_width / native_width),
 ceil(right * image_width / native_width))
```

Clip both ends to `[0, image_width]` and perform the analogous calculation separately for the vertical axis. Integer division avoids boundary drift and correctly handles negative origins. Separate axis ratios matter because screenshot height and width are rounded independently during resizing. A clipped empty interval returns null.

This is a pointer-coordinate contract, not a description of every color mixed into a resampled pixel. The screenshot's image resampler can blend native areas that are not themselves selectable as distinct integer screenshot positions.

## Validation

Commit `33980f5` passed 361 unit tests, including six new coordinate tests. An independent enumerated oracle checks all small rectangles across multiple native/image ratios, clipping, empty rectangles, upscaling, negative origins and last-pixel boundaries. Tests also cover tall-image scaling and prove that enriching response copies does not alter native cached window/popup data or layout signatures.

Real GTK decorated and borderless windows were checked on a private 1440×1000 Xvfb desktop at returned widths 1280, 777 and 321. Independent `xwininfo` bounds and `xdotool getmouselocation` confirmed the image rectangles and integer-center pointer mapping, including partially off-screen windows and fullscreen last pixels. A real unmanaged GTK popup was independently tested at returned width 333 with the same pointer-location oracle. Both live suites passed as ordinary desktop UID 1001 with unchanged source fingerprints; artifacts are under `artifacts/coordinates/`.

These additions change response metadata only. Snapshot expiry, signatures, identities, native geometry and pointer validation retain their existing behavior.
