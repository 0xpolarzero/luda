# Tool reference

Generated from the registered MCP tools by `python scripts/build_tools.py`.

Window and element IDs come from observations. Coordinates use returned screenshot pixels. Read `effect` and the named verification before deciding whether to repeat an action.

## `desktop_control`

```python
desktop_control(action: Literal['status', 'pause', 'resume']='status')
```

Pause/resume cooperating agent input across servers on this display. Pause interrupts at the next checkpoint; already-delivered input is not undone. Observation remains available. This does not stop arbitrary external input programs.

## `desktop_status`

```python
desktop_status()
```

Return recent operation outcomes after timeout/cancellation. No input text or screenshots are retained.

## `desktop_doctor`

```python
desktop_doctor()
```

Check actual display access, desktop session, dependencies and accessibility availability.

## `desktop_applications`

```python
desktop_applications(query: str='', limit: int=50)
```

Find installed desktop applications by name, description or ID. Returns application_id and file/URI support; works while input is paused. Use an exact returned ID with desktop_launch.

## `desktop_launch`

```python
desktop_launch(application_id: str, files_or_uris: list[str] | None=None)
```

Launch an installed application by its desktop_applications ID, optionally opening absolute existing paths or URIs. No command strings. Returns dispatched, not ready: inspect desktop_windows for the new or existing app; never blindly retry an uncertain launch.

## `desktop_windows`

```python
desktop_windows()
```

List window identities, titles, process identity, focus and native client bounds.

## `desktop_activate`

```python
desktop_activate(window_id: str)
```

Activate a window from desktop_windows and verify focus. Observe again afterward.

## `desktop_observe`

```python
desktop_observe(max_width: int=1280)
```

Return screenshot plus window layout and a 15-second snapshot ID. Coordinates are image pixels.

## `desktop_inspect`

```python
desktop_inspect(window_id: str, limit: int=150, name: str | None=None, role: str | None=None, states: list[str] | None=None, max_depth: int=30)
```

Inspect a window or find controls by name/role substring and required states. Returns bounded tree, parent IDs, supported actions and 60-second element IDs. Empty matches and unavailable accessibility are distinct.

## `desktop_read_text`

```python
desktop_read_text(element_id: str, limit: int=16000)
```

Read exact accessible text, preserving whitespace. Protected fields are unsupported. Maximum 1 MB.

## `desktop_type`

```python
desktop_type(element_id: str, text: str, mode: Literal['insert', 'replace']='insert')
```

Type into an editable element and verify exact readback. Default insert preserves surrounding text and replaces the selection; replace changes the entire field. Preserves Unicode/LF/tabs, never adds a submit key.

## `desktop_type_secret`

```python
desktop_type_secret(element_id: str, text: str)
```

Replace an observed protected field. Never reads back or echoes the value, uses no clipboard, and reports dispatched only. Requires protected EditableText support; submission is a separate action.

## `desktop_choose`

```python
desktop_choose(element_id: str, extend: bool=False)
```

Choose an observed list option, radio or supported combo option and verify selection. Default makes the choice exclusive; extend preserves other list selections. Open collapsed options and inspect first.

## `desktop_paste`

```python
desktop_paste(window_id: str, text: str, shortcut: Literal['ctrl_v', 'ctrl_shift_v', 'shift_insert'] | None=None)
```

Paste through CLIPBOARD when semantic typing is unavailable. Chooses common app shortcut from window class, with optional override. Destination is unverified; inspect dialogs/read back. Terminals can execute pasted newlines.

## `desktop_press_keys`

```python
desktop_press_keys(window_id: str, chord: str)
```

Send one deliberate chord, e.g. ctrl+s, ctrl+shift+v, Return, Tab, Escape. Requires target focus; never use this to type text.

## `desktop_click`

```python
desktop_click(window_id: str, snapshot_id: str, x: float, y: float, button: Literal['left', 'middle', 'right']='left', count: Literal[1, 2, 3]=1)
```

Click screenshot-image coordinates in the active window or its observed menus. Rejects stale or covered targets.

## `desktop_scroll`

```python
desktop_scroll(window_id: str, snapshot_id: str, x: float, y: float, direction: Literal['up', 'down', 'left', 'right'], ticks: int=3)
```

Scroll 1–20 wheel ticks at a point in the observed active target. Read resulting state to confirm.

## `desktop_drag`

```python
desktop_drag(window_id: str, snapshot_id: str, x: float, y: float, end_x: float, end_y: float, button: Literal['left', 'middle', 'right']='left')
```

Drag between two observed points inside the same active window; always attempts button release. Use desktop_drag_to for another destination window.

## `desktop_focus_element`

```python
desktop_focus_element(element_id: str)
```

Request accessibility focus in the active window. Inspect to confirm focused state.

## `desktop_invoke`

```python
desktop_invoke(element_id: str, action: str)
```

Invoke an exact action name returned by inspect. Completion means dispatch, not verified application outcome.

## `desktop_select`

```python
desktop_select(element_id: str, start_offset: int, end_offset: int)
```

Select a text range using Unicode code-point offsets, or place caret when equal; verify the result.

## `desktop_set_value`

```python
desktop_set_value(element_id: str, value: float)
```

Set a numeric control to a value within its inspected range and verify the actual value.

## `desktop_set_checked`

```python
desktop_set_checked(element_id: str, checked: bool)
```

Set a checkable control to the requested state; avoid a blind toggle when it already matches.

## `desktop_set_expanded`

```python
desktop_set_expanded(element_id: str, expanded: bool)
```

Expand or collapse a supported control and verify state. Reinspect newly exposed children.

## `desktop_window`

```python
desktop_window(window_id: str, action: Literal['move', 'resize', 'maximize', 'minimize', 'restore', 'close', 'workspace'], x: int | None=None, y: int | None=None, width: int | None=None, height: int | None=None, workspace: int | None=None)
```

Manage one window. move uses frame x/y; resize uses client width/height; workspace requires its index. Other actions take no extra parameters. A close can open a save dialog.

## `desktop_workspaces`

```python
desktop_workspaces(workspace: int | None=None)
```

List workspaces, or switch to an existing index and verify the active workspace.

## `desktop_hover`

```python
desktop_hover(window_id: str, snapshot_id: str, x: float, y: float)
```

Move the pointer to a recent observed point without clicking; observe tooltips/submenus afterward.

## `desktop_drag_to`

```python
desktop_drag_to(source_window_id: str, target_window_id: str, snapshot_id: str, x: float, y: float, end_x: float, end_y: float, button: Literal['left', 'middle', 'right']='left')
```

Drag from the active source into a second observed window. Coordinates refer to one screenshot. Verify transfer in the applications; dispatch does not prove a drop was accepted.

## `desktop_wait`

```python
desktop_wait(condition: Literal['window_present', 'window_absent', 'window_active', 'text_equals', 'text_contains'], window_id: str | None=None, element_id: str | None=None, text: str | None=None, timeout: float=5)
```

Wait up to 10 seconds for an observable condition without repeating input. Window conditions use window_id; text conditions use element_id and text. A timeout returns matched=false.
