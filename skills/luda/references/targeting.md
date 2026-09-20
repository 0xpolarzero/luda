# Targeting and movement

## Find a window and its controls

```python
desktop_windows(query="Notes", limit=50, offset=0)
desktop_inspect(window_id="<window_id>", role="entry")
```

Window queries filter title/class. Each paginated call is a new enumeration, so do not assume a frozen list. Use actual identity and context when multiple windows match. Routine activation is unnecessary: native semantics can operate in the background and foreground input activates automatically. Explicit activation is useful to reveal a covered target; observe again afterward.

`desktop_inspect` returns native accessibility `nodes`, parent IDs, roles, names, states, and supported actions. Optional browser `text_fields` use separate provider-bound IDs. Filter known controls with `name`, `role` (substring matches), or required `states`; increase `limit` or `max_depth` when justified by truncation. Defaults are 150 nodes and depth 30. Read returned availability and coverage before interpreting an empty result. It can mean no matches, incomplete traversal, or unsupported accessibility.

Use the same server's returned element ID within 60 seconds. Reinspect after navigation, document replacement, sorting/filtering, or `STALE_TARGET`. Do not substitute another control solely because it has a similar label.

## Ground image coordinates

```python
desktop_observe(max_width=1280)
desktop_click(window_id="<window_id>", snapshot_id="<snapshot_id>", x=420, y=310)
```

The numbers above are illustrative: choose real integer pixels from the returned image. `max_width` may resize the screenshot. Window/popup `image_bounds` map into that image; their integer center is `x + width//2, y + height//2`. A null image rectangle contains no selectable integer pixel at that scale. A larger observation can make small targets resolvable.

Do not pass native window `bounds`, `frame_bounds`, accessibility bounds, or remembered coordinates directly to image-pointer tools. If using semantic actions, no coordinate conversion is necessary.

A snapshot remains usable for at most 15 seconds, subject to cache retention, window identity/geometry, focus, display topology, active workspace, and coverage checks. `STALE_OBSERVATION` means observe again and identify the target anew. Even a valid snapshot does not prove unchanged content: an application can replace a button without moving its window.

Windows can cover each other; covered targets are refused. Activate the intended window and observe rather than clicking through an obstruction. Menus/submenus owned by the window use that window's ID and observed popup `image_bounds`; menu rows are often better exposed through accessibility after opening.

## Pointer operations

| Intent | Call shape |
|---|---|
| Single/right/double/triple click | `desktop_click(window_id, snapshot_id, x, y, button="left", count=1)`; count 1–3 |
| Reveal hover tooltip or submenu | `desktop_hover(window_id, snapshot_id, x, y)`, then observe |
| Scroll under the pointer | `desktop_scroll(window_id, snapshot_id, x, y, direction="down", ticks=3)`; ticks 1–20 |
| Drag within one window | `desktop_drag(window_id, snapshot_id, x, y, end_x, end_y)` |
| Drag to another window | `desktop_drag_to(source_window_id, target_window_id, snapshot_id, x, y, end_x, end_y)` |

For dragging, ground both endpoints in the same screenshot. Drags activate their source automatically after validating both endpoints; raising the source must not cover the destination. Luda attempts button release even on interruption; the receipt does not prove the destination accepted a drop. Check the destination application and, for moves, the source. Reobserve after scrolling before selecting newly visible content.

## Window layout and workspaces

`desktop_window(window_id, action=...)` takes only parameters appropriate to its action:

| Action | Extra arguments and meaning |
|---|---|
| `move` | `x`, `y`: native frame position |
| `resize` | `width`, `height`: native client size |
| `workspace` | `workspace`: an existing workspace index |
| `maximize`, `minimize`, `fullscreen`, `raise`, `restore`, `close` | No geometry arguments |

This tool's geometry parameters are native pixels, unlike image-pointer coordinates. Read the returned actual geometry: the window manager can constrain requested sizes/positions. `raise` preserves focus; use `desktop_activate` if focus is needed. `restore` exits fullscreen, maximization, and minimization; a historical geometry comparison may be unknown and does not force saved bounds. Closing can reveal an unsaved-document dialog; it does not answer it.

Call `desktop_workspaces()` to discover indices; `desktop_workspaces(workspace=1)` switches to a returned index and verifies it. Every dispatched switch invalidates this server's snapshots, including a request for the already active workspace. Observe again. Sampled external workspace changes also invalidate matching snapshots, but a switch-and-return entirely between checks is not continuously tracked.
