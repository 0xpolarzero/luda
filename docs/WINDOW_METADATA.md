# Batched window metadata

`X11.window_metadata(xids)` accepts at most 512 positive XIDs and uses one isolated, deadline-bound helper. It returns:

```text
windows: {integer_xid: {
  bounds: {x,y,width,height}, generation: string,
  frame_extents: {left,right,top,bottom} | null,
  wm_class: [instance,class] | [], pid: integer | null,
  unavailable_properties: [{property,code}]
}}
unavailable: [{xid,code}]
requested_count, unique_requested_count, returned_count, unavailable_count
```

Generation is checked before and after the read. A destroyed/recreated resource or invalid generation property is omitted with an explicit reason; one malformed generation does not hide other windows. Missing or invalid optional metadata is retained as a diagnostic rather than silently represented as complete information. Callers should verify the returned PID against any earlier enumeration row before issuing an actionable window identity.

Frame extents must be exactly four CARDINAL/32 values, each at most 65535. WM_CLASS must be STRING/8 containing exactly two NUL-terminated strings, bounded to 1024 total bytes and 512 per component. UTF-8 is decoded directly; legacy Latin-1 class names remain readable. Oversized and malformed values are not returned. Neither metadata content nor geometry is claimed to be an atomic application-content snapshot; the generation check establishes resource lifetime.

The GTK live test independently checked ten actual windows against xwininfo geometry, xprop frame extents and fixture class/PID values. The former two-helper-plus-ten-xprop path averaged 50.23 ms, versus 23.26 ms for one metadata batch. Synthetic bad properties, invalid generation and a missing resource produced the documented diagnostics and counts. A separate disposable-Xvfb test returned all 512 resources in 0.153 seconds and rejected 513 before dispatch. Timings describe this VM and workload, not a general latency guarantee.

Tests: `tests/test_window_metadata.py`, `tests/live_window_metadata.py` (shared-desktop lease required), and `tests/live_window_metadata_capacity.py` (owns a disposable Xvfb).
