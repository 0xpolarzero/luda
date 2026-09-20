# Optional capabilities

Check `desktop_doctor` and the tool result before assuming an optional dependency is present. Default Linux computer use does not require the temporary-browser provider, OCR, image matching, or recording. Missing one should not prevent independent available tools from being used.

## Temporary browser and ordinary fields

```python
desktop_open_browser(url="https://example.com", lifetime="temporary_session")
desktop_inspect(window_id="<returned window_id>", role="entry")
```

Use this only when a **fresh, disposable** browser fits the task. It never attaches an existing profile. Browser, profile, cookies, and unsaved content are removed on MCP disconnect, backend close, or reconnect; downloads kept inside its temporary storage disappear too. Save needed data to a deliberate external path before closing the session.

The operator must provision the optional browser dependencies and a compatible Chromium executable; runtime does not download a browser or disable its sandbox as a fallback. Doctor's availability indicates dependency/executable presence, not a successful launch or compatibility with every website.

Inspection returns provider-bound `text_fields` for ordinary HTML text/search/url/tel inputs and textareas. Native accessibility `nodes` remain separate for buttons and other UI. Use the fields' IDs with `desktop_read_text`, `desktop_focus_element`, `desktop_select`, and `desktop_type`. They retain DOM node/document identity and expire after 60 seconds; navigation/replaced nodes invalidate them. Same-node application repurposing still requires contextual judgment.

```python
desktop_focus_element(element_id="<text_field_id>")
desktop_select(element_id="<text_field_id>", start_offset=0, end_offset=4)
desktop_type(element_id="<text_field_id>", text="New")
```

Ordinary fields use native browser text input and do not replace the clipboard. Read metadata such as `multiline` and `line_break_semantics`; textarea LF/tabs do not require paragraph options. Single-line fields refuse LF/tabs. Exact field readback does not prove autocomplete choice, keyboard-event behavior, application commit, or saving.

Public offsets are Unicode code points. Native operations refuse positions inside joined emoji/combining graphemes with `UNSUPPORTED_TEXT_BOUNDARY`; missing segmentation can produce `TEXT_BOUNDARY_UNAVAILABLE`. Do not silently widen ranges or retry an uncertain input. Whole-field boundaries remain distinct from interior boundaries.

Observed password inputs advertising `secret_entry_supported=true` support only explicit `desktop_type_secret`; ordinary read/type refuse them. Secret replacement is clipboard-free and dispatch-only, refuses LF/CR and declared maxlength overflow, and never submits.

The provider has deliberately bounded scope: ordinary supported light-DOM fields; no attachment to existing profiles, arbitrary script execution, frames, shadow-root traversal, or generic rich-editor support. Frames or extra owned pages/windows can make the provider unavailable; `desktop_inspect` can still return independently available native nodes while `text_fields` is empty. Cached owned IDs do not silently fall back to native input.

Composition monitoring refuses active or unknown composition before focus/selection/input. A real IME end can leave the monitor conservatively active; there is no automatic Escape, guessed commit, or override. Navigation creates a fresh document context but can discard work, so it is not a generic recovery step. Focus/content can race between checks and dispatch: an uncertain error can include text delivered elsewhere. Inspect before retrying.

A cleanup-unconfirmed error blocks another owned browser in the same backend. Do not repeatedly open browsers to escape cleanup uncertainty; use [recovery](recovery.md) and retain needed evidence.

## OCR

```python
desktop_ocr(snapshot_id="<snapshot_id>", language="eng", limit=200)
```

OCR operates locally on that retained screenshot; it does not capture again. It requires Tesseract and the requested language. Word boxes are **returned-image pixels** and scores are uncalibrated candidates, not exact/current text, semantic identity, or permission to click.

An expired/evicted snapshot requires a deliberate new observation. A layout-valid snapshot can still have obsolete content. Identify the intended current control before acting, especially where repeated labels or changing content make OCR ambiguous. Missing OCR does not prevent manual visual grounding or native accessibility.

## Image matching

```python
desktop_match_image(
    template_snapshot_id="<source_snapshot_id>",
    template_bounds={"x": 40, "y": 70, "width": 32, "height": 32},
    snapshot_id="<target_snapshot_id>",
    threshold=0.95,
    limit=20,
)
```

Use a genuinely observed source crop, not these sample coordinates. Both screenshots must still be retained/fresh and have the same image scale. The source crop can be historical (for example before a window moved); the target must retain its captured layout. Bounds use source returned-image pixels, x/y are nonnegative, width/height 8–512. Threshold is finite 0–1 and limit 1–100. Optional system OpenCV is required.

Results use target returned-image pixels. Scores are uncalibrated visual correlations; distinct duplicates can remain, flat templates are refused, and overlapping placements are suppressed. Do not silently choose the first candidate when identity is ambiguous. Matching sends no input and captures no new image.

## Screen recording

Use recording only for an explicitly requested recording of the selected display.

```python
desktop_recording(action="start", max_seconds=20)
desktop_recording(action="stop", recording_id="<returned recording_id>")
```

Keep the ticket. `start` means capture began, not that a valid file exists. Only `status`/`stop` with `state="complete"` and `playable_verified=true` supplies a validated file. Recording is 10 fps, at most 1280×720, 1–60 seconds, and **has no audio**. Local ffmpeg/ffprobe are required.

Temporary private files are deleted on backend close/reconnect/server death. If the task requires a durable recording, explicitly copy the completed file elsewhere using available file tools before closure, then `desktop_recording(action="delete", recording_id=...)`. Stop/delete work while paused. Do not infer a saved artifact from a start receipt or stable screen pixels.
