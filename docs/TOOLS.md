# Tool reference

Generated from the registered MCP tools by `python scripts/build_tools.py`.

Window and element IDs come from observations. Coordinates use returned screenshot pixels. Read `effect` and the named verification before deciding whether to repeat an action.

## `desktop_control`

```python
desktop_control(action: Literal['status', 'pause', 'resume']='status')
```

Pause/resume cooperating agent input across servers on this display. Pause interrupts at the next checkpoint; already-delivered input is not undone. Observation remains available. This does not stop arbitrary external input programs.

## `desktop_recording`

```python
desktop_recording(action: Literal['start', 'status', 'stop', 'delete'], recording_id: str | None=None, max_seconds: int=30)
```

Explicit temporary screen recording: start, status, stop or delete by ticket. Start records only this X11 display, no audio, at 10fps and at most 1280×720 for 1–60 seconds. Start is not completed-file verification; stop/status return a path only after decoding verifies completion. Files are private, bounded and deleted on backend close/reconnect/server death; explicitly copy elsewhere before closure to save durably. Stop/delete remain usable while paused. Optional local ffmpeg/ffprobe required.

## `desktop_match_image`

```python
desktop_match_image(template_snapshot_id: str, template_bounds: ImageBounds, snapshot_id: str, threshold: float=0.95, limit: int=20)
```

Find historical visual candidates from a selected screenshot crop in another retained screenshot. template_bounds requires x, y, width and height in source returned-image pixels; x/y are nonnegative and width/height are 8–512. Both IDs must be retained and fresh, from the same server and image scale; only the target must still have its captured layout. Historical source crops may come from a window that moved. Results use target returned-image pixels. Threshold is finite 0–1, limit 1–100; scores are uncalibrated correlation, never semantic identity or click permission. Returns non-overlapping candidates, preserving distinct duplicates; flat templates are refused. No new capture or input. Optional system OpenCV required.

## `desktop_ocr`

```python
desktop_ocr(snapshot_id: str, language: str='eng', limit: int=200)
```

Read uncertain local OCR word candidates from this exact retained screenshot, never a new capture. Returns image-pixel boxes and uncalibrated engine scores, not exact text or action permission. Snapshot expires after 15 seconds or cache eviction; changed layout is refused. Optional Tesseract and the selected language must be installed. No input is sent.

## `desktop_status`

```python
desktop_status()
```

Return recent operation outcomes after timeout/cancellation. This operation history excludes input text and screenshots.

## `desktop_report`

```python
desktop_report()
```

Return a sanitized bug-report JSON: fixed environment/dependency versions, projected health and up to 32 recent operation IDs/methods/effects/timings, fixed error codes and semantic verbs from this MCP process. Excludes desktop content, paths, exceptions and action arguments. No files, uploads or replay. Supply synthetic repro steps separately; explicitly save/delete the returned report if needed.

## `desktop_recover_input`

```python
desktop_recover_input()
```

Retry cleanup of this server's interrupted supervised input, without replaying keys/clicks or resuming a paused desktop. Uses each operation's original session; a replaced X server is left untouched. Unproven cleanup stays blocked. Returns pending_count and recovery proofs; observe again before acting. Returns BUSY if another operation is still running.

## `desktop_reconnect`

```python
desktop_reconnect(session_pid: int | None=None)
```

Reconnect this MCP connection to a running XFCE session owned by this account after a desktop restart. Omit PID only when exactly one session exists. Validates display and bus before replacing the backend; failed validation preserves it. Returns BUSY during other operations, never restarts apps or replays input. All prior window, element and screenshot IDs expire; observe again. The selected display's pause state remains in force. Temporary owned browsers/profiles are closed and unsaved content is lost; browser_cleanup=unconfirmed reports cleanup that could not be proved.

## `desktop_doctor`

```python
desktop_doctor()
```

Check actual display access, desktop session, dependencies and accessibility availability. Reports driver version and content identities for tool declarations and the server-bundled skill; the latter does not identify the skill loaded by your agent.

## `desktop_applications`

```python
desktop_applications(query: str='', limit: int=50)
```

Find installed desktop applications by name, description or ID. Returns application_id and file/URI support; works while input is paused. Use an exact returned ID with desktop_launch.

## `desktop_open_browser`

```python
desktop_open_browser(url: str, lifetime: Literal['temporary_session'])
```

Open a fresh owned Chromium with explicit temporary_session lifetime. Browser/profile and unsaved content are deleted on server disconnect, backend close or reconnect. Requires optional browser dependencies and configured executable; never downloads automatically or attaches existing profiles. Inspect text_fields for ordinary HTML fields, cooperating paragraph editors and explicit password-only secret entry. Ordinary protected-field operations, unregistered rich editors and frames are unsupported.

## `desktop_launch`

```python
desktop_launch(application_id: str, files_or_uris: list[str] | None=None, wait_timeout: float=1.0)
```

Launch an installed application by its desktop_applications ID, optionally opening absolute existing paths or URIs. Returns dispatched with process-bound window candidates observed for wait_timeout seconds (default 1, range 0–3; 0 skips observation). Candidates do not prove document readiness; singleton association is never guessed. Inspect candidates or desktop_windows before acting; never blindly retry an uncertain launch.

## `desktop_windows`

```python
desktop_windows(query: str | None=None, limit: int=50, offset: int=0)
```

List window identities, titles, focus and client bounds, optionally filtering title/class. Returns counts, unavailable rows and next_offset when paginated. Each call is a fresh enumeration.

## `desktop_activate`

```python
desktop_activate(window_id: str)
```

Activate a window from desktop_windows and verify focus. Observe again afterward.

## `desktop_observe`

```python
desktop_observe(max_width: int=1280)
```

Return screenshot plus window layout and a 15-second snapshot ID. Pointer coordinates and window/popup image_bounds use returned-image pixels; bounds/frame_bounds remain native X11 root pixels. image_bounds is null when no integer screenshot pixel maps into the client. Use integer image points.

## `desktop_inspect`

```python
desktop_inspect(window_id: str, limit: int=150, name: str | None=None, role: str | None=None, states: list[str] | None=None, max_depth: int=30)
```

Inspect a window or find controls by name/role substring and required states. Returns bounded tree, parent IDs, supported actions and 60-second element IDs. Owned browser text_fields have distinct provider-bound IDs for ordinary HTML fields and explicitly cooperating paragraph editors; role="entry" filters for fields. Field metadata describes line breaks and write scope. When extra owned pages/windows or frames make the owned provider unavailable, native nodes remain independently inspected; owned_browser reports unavailable/code and text_fields is empty. Cached owned fields still refuse unsupported scope; no mutation fallback. Empty matches and unavailable accessibility are distinct.

## `desktop_read_text`

```python
desktop_read_text(element_id: str, limit: int=16000)
```

Read accessible text and representation metadata, preserving whitespace. limit counts Unicode code points (default 16000, maximum 1000000), not bytes. Opaque embedded objects are not exact logical plain text: check plain_text_verification_supported. Normalization reads the bounded full field; a smaller limit does not enable streaming. Protected fields are refused. Generic native readback reports composition known=false, active=null; pending preedit is not checked.

## `desktop_type`

```python
desktop_type(element_id: str, text: str, mode: Literal['insert', 'replace']='insert', line_breaks: Literal['paragraph', 'hard_break'] | None=None, transport: Literal['native', 'clipboard']='native')
```

Type into an editable element and verify exact readback. Owned browser-native insertion refuses positions inside a grapheme; offsets still count code points. For a cooperating rich editor, LF requires an explicit supported line_breaks policy: paragraph, or hard_break only when the app declares its Shift+Enter binding. Readback distinguishes those node types even though both contribute logical LF. Native input supports whole-field replace or append at the end. Explicit transport="clipboard" supports selected code-point ranges and leaves the final nonempty segment in CLIPBOARD until another owner replaces it or the temporary session closes. Empty text deletes the selection without replacing CLIPBOARD; actual new formatting is reported. Default insert preserves surrounding text and replaces the selection; replace changes the entire field. Preserves Unicode/LF/tabs, never adds a submit key. Exact readback does not prove application commit or guarantee autocomplete events; inspect the result before an explicit commit or suggestion selection. Rich-editor final receipts may report verified, uncertain and not-started segment counts; these are not save confirmation or instructions to replay the remainder.

## `desktop_type_secret`

```python
desktop_type_secret(element_id: str, text: str)
```

Replace an observed protected field. Never reads back or echoes the value, uses no clipboard, and reports dispatched only. Requires native protected EditableText or an owned password input with known inactive composition. Owned input rejects LF/CR and declared maxlength overflow; submission is separate. Applications control their own masking, which can change during input.

## `desktop_choose`

```python
desktop_choose(element_id: str, extend: bool=False, range_end_id: str | None=None)
```

Choose an observed list/radio/combo option or a visible table cell and verify selection. A table cell selects its whole row. Default makes the choice exclusive; extend preserves other list or table-row selections. Scroll offscreen rows into view and inspect again; reacquire after sorting/filtering. Open collapsed options and inspect first. range_end_id selects an inclusive range of at most 50 visible list items or table rows, using two endpoints from the same inspection; reversed endpoints are allowed. Every intermediate item must be inspected in unchanged order, and table endpoints use the same column. extend adds the range; otherwise it replaces the selection. Duplicate range labels, unsupported providers and unloaded gaps are refused. List replacement verifies one clear then each addition; an already exact set is unchanged. Limits: 50 range items and 500 selected items. Selection step receipts are historical verification, never instructions to retry a remainder.

## `desktop_paste`

```python
desktop_paste(window_id: str, text: str, shortcut: Literal['ctrl_v', 'ctrl_shift_v', 'shift_insert'] | None=None)
```

Paste through CLIPBOARD when semantic typing is unavailable. Chooses common app shortcut from window class, with optional override. Destination is unverified; inspect dialogs/read back. Terminals can execute pasted newlines.

## `desktop_press_keys`

```python
desktop_press_keys(window_id: str, chord: str, count: int=1)
```

Send a deliberate chord, e.g. ctrl+s, ctrl+plus, ctrl+minus, Return, Tab, Escape or Down. Punctuation uses X11 names (plus, equal, bracketleft, slash); implicit Shift follows the current layout. count is 1–20 complete press/release repetitions, default 1. Revalidates target identity, focus and input state between repetitions; stops on the first failure and never retries. Requires target focus, refuses held keys/buttons, and preserves the current keyboard mapping. Unavailable symbols return UNSUPPORTED_KEYMAP; text belongs in desktop_type. When a final companion receipt is available, progress reports fully dispatched, possibly partial and not-started repetitions. Dispatched count is not application completion.

## `desktop_click`

```python
desktop_click(window_id: str, snapshot_id: str, x: float, y: float, button: Literal['left', 'middle', 'right']='left', count: Literal[1, 2, 3]=1)
```

Click screenshot-image coordinates in the active window or its observed menus. Rejects expired snapshots, changed window layout/identity and covered targets. Snapshot validity does not prove unchanged application content; observe again after content transitions before selecting a control.

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

Request element focus in the active window; owned browser fields refuse active/unknown composition before focus. Inspect to confirm focused state.

## `desktop_invoke`

```python
desktop_invoke(element_id: str, action: str | None=None)
```

Invoke the sole action returned by inspect, or supply its exact action name. Multiple actions require an explicit choice; no click/press naming guess is needed for a single-action button. Completion means dispatch, not verified application outcome.

## `desktop_select`

```python
desktop_select(element_id: str, start_offset: int, end_offset: int)
```

Select a text range using Unicode code-point offsets, or place the caret when equal; verify the result. For owned-browser fields, call desktop_focus_element first. Cooperating paragraph editors with the updated bridge accept code-point ranges; writing at a middle range or caret requires desktop_type with explicit transport="clipboard". Their default native typing supports whole-field replacement or append at the end. Ordinary HTML fields support code-point ranges; native edits inside graphemes can be refused.

## `desktop_set_value`

```python
desktop_set_value(element_id: str, value: float)
```

Set a numeric control within its inspected range and verify its accessibility numeric value. Displayed formatting and application commit may differ; inspect/read both, then explicitly commit only when intended.

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
desktop_window(window_id: str, action: Literal['move', 'resize', 'maximize', 'minimize', 'fullscreen', 'raise', 'restore', 'close', 'workspace'], x: int | None=None, y: int | None=None, width: int | None=None, height: int | None=None, workspace: int | None=None)
```

Manage one window. move uses frame x/y; resize uses client width/height; workspace requires its index. fullscreen requests WM fullscreen; restore exits fullscreen/maximization/minimization; raise changes stacking without activation. Other actions take no extra parameters. Close reports an owned blocking dialog without confirming it. Geometry actions return fresh same-generation client/frame bounds and WM state; move/resize distinguish matched from nonmatching requests without upgrading dispatched effects. Restore compares captured pre-maximize bounds when observed geometry, state and size hints remain consistent; otherwise comparison is unknown. No saved geometry is forced, and unobserved external changes cannot be ruled out.

## `desktop_workspaces`

```python
desktop_workspaces(workspace: int | None=None)
```

List workspaces, or switch to an existing index and verify the active workspace. Every dispatched switch expires this server’s screenshots, even when requesting the current workspace; observe again before using coordinates. External workspace changes between observations are not continuously tracked.

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
desktop_wait(condition: Literal['window_present', 'window_absent', 'window_active', 'text_equals', 'text_contains', 'element_present', 'element_absent', 'pixels_stable'], window_id: str | None=None, element_id: str | None=None, text: str | None=None, timeout: float=5, name: str | None=None, role: str | None=None, states: list[str] | None=None, stable_for: float=0.3)
```

Wait up to timeout (0–10 seconds) for an observed condition. window_present/window_absent/window_active require only window_id, never a title in text; discover title matches with desktop_windows(query=...). text_equals/text_contains require only element_id and text. element_present/element_absent require window_id plus at least one name/role substring or states filter; they search native accessibility nodes, and absence requires complete coverage. pixels_stable requires window_id and optionally stable_for (0.1–10 seconds, at most timeout); it samples the client rectangle, not general application idleness. Omit parameters belonging to other condition types.
