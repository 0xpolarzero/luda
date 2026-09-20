# First-use media workflow, 2026-09-20

Source: `dc4dc70` (current main at worktree creation), dedicated venv, actual
stdio MCP, ordinary `silo-desktop` UID 1001, owned Xvfb `:143`, 900×650,
owned xfwm4/GTK fixture and D-Bus session. No shared `:1` interaction.
Read AGENTS.md, the Luda skill, README and recording documentation, then actual
`tools/list`; did not inspect implementation or existing live test scripts.
The recording documentation includes prior evidence, so this is not a fully
documentation-blind trial. Fixture positions, texture and label were randomized;
its separate geometry/text oracle was first read after calls 1–7 completed.

## First attempts and interpretation

All intended public tool calls succeeded on their first attempt. The initial
shell worktree command omitted its working directory and failed harmlessly;
retry used the repository cwd. During the final harness smoke check, the external
driver tried to read a response before it had been written; waiting for file
existence resolved that harness race. Editing the original shell runner while
its first instance remained alive caused an unterminated-quote error at shell
exit (after MCP close); the fresh final-runner smoke exited zero. Future runs
should keep launcher source immutable throughout execution. No tool retry or hidden expected assertion was
used to manufacture the successful workflow.

1. `desktop_doctor` clearly reported UID/display, OCR/recording availability and
   readiness. `desktop_observe` supplied a screenshot and image-space rectangles.
2. Visually read `MEDIA CHECK 86727` and selected the first textured icon at
   `{x:163,y:259,width:56,height:56}` from the screenshot. `desktop_ocr` returned
   all three label words correctly, plus spurious `BA` over both textured icons
   (engine confidence 48.098774). This is recognition uncertainty, not verified
   application text. The result explicitly calls the values historical,
   uncalibrated candidates and does not authorize clicks.
3. `desktop_match_image` using that retained screenshot for both source and
   target found two separate candidates, `(163,259)` and `(526,259)`, each score
   1.0. These are indistinguishable visual duplicates; ranking establishes no
   unique identity. No icon was selected or clicked. The later independent GTK
   oracle exactly matched both boxes and the label.
4. `desktop_recording(start,max_seconds=30)` returned `dispatched`, one captured
   frame and a ticket, with clear temporary-retention guidance. Stop returned
   `complete`, `playable_verified=true`, `end_reason=requested_stop`; status
   confirmed that file. Explicit same-UID `shutil.copyfile` saved the completed
   artifact outside its temporary recording directory, then independent ffprobe
   and full ffmpeg decode verified the copy: 719,940 bytes, MPEG-4, 900×650,
   duration 19.168831 seconds. Delete returned `verified/deleted`; filesystem
   inspection confirmed the original path disappeared and the copy remained.
   The copy also survived MCP close. SHA-256 is retained in `transcript.json`.

Lifetime and uncertainty semantics were prominent in both skill and returned
results. The ticket workflow was intuitive; no arbitrary output-path option
was needed because the skill explicitly instructs a separate durable copy.

## Deliberate negative probes after the first workflow

- Expired OCR ID: `STALE_OBSERVATION`, effect none, explicit instruction to
  observe again. Fresh observation recovered normally.
- Duplicate matching with `limit=1`: one candidate plus `truncated=true`; a
  singleton page does not imply a unique match.
- Blank 30×30 crop: `MATCH_FLAT_TEMPLATE`, effect none, useful crop guidance.
- `{left,top,width,height}` crop: `INVALID_ARGUMENT`, effect none, explanatory
  `template_bounds requires integer x, y, width and height in source image pixels`.

The last probe reproduces a minor schema discoverability gap: `template_bounds`
is declared only as an arbitrary string→integer map, with no required coordinate
keys or property description. Correct names were inferred from observe's
`image_bounds`. Runtime refusal is clear and safe; the schema could describe the
actual rectangle shape directly. This was a deliberate boundary probe, not a
first-use failure. No production change is included.

## Reproduction

The included harness preserves one real MCP connection and writes tools/list,
requests, responses and screenshot files separately. The fixture oracle must
remain unread until tool attempts are complete. Install the project into this
worktree's `.venv`, then from the repository root run as the ordinary desktop
account (or use `runuser -u silo-desktop --` from root):

```sh
xvfb-run -a -s '-screen 0 900x650x24 -nolisten tcp -noreset' \
  dbus-run-session -- sh evidence/media-usability/run.sh
```

The runner prints a fresh private request directory. Write sequential
`request-1.json`, `request-2.json`, etc. containing
`{"name":"desktop_doctor","arguments":{}}` and then
`{"name":"desktop_observe","arguments":{}}`. Read each corresponding response
and screenshot, choose crop coordinates from that new screenshot, then follow
the calls retained in `transcript.json`, substituting fresh IDs/coordinates.
Requests are consumed only in sequence. Finish with `{"close":true}` in the
next request file. Keep observe→OCR/match within the advertised 15 seconds;
explicitly reobserve on expiration. Do not reuse this run's crop or text as an
assertion for the randomized fixture. The fixture requires system PyGObject;
WM, Xvfb, Tesseract, OpenCV, FFmpeg and ffprobe were available locally.

The final harness changed its initial fixed request directory to a fresh mode
0700 `mktemp` directory. An additional actual MCP observe/close smoke run
verified that packaging change. `transcript.json` preserves the original trial,
including negative results; synthetic PNG/MP4 files remain local rather than
being committed. This small probe does not qualify audio, dynamic video
content, platform portability, OCR accuracy generally, or arbitrary icon sets.
