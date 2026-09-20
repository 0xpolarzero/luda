# RTL visual navigation and logical text

DATA-10 requires: “RTL layout: visual navigation and text storage semantics remain
distinct.” The real GTK fixture in `tests/rtl_fixture.py` exposes an RTL entry with
mixed Arabic, Hebrew, Latin letters, digits and emoji. `tests/live_rtl.py` drives
it exclusively through public stdio MCP tools and uses the widget's independent
logical storage, selection bounds and Pango cursor geometry as oracles.

Run as the ordinary desktop account from an installed locked-dependency checkout:

```bash
.venv/bin/python tests/live_rtl.py
```

The test creates private XDG directories before a private Xvfb/D-Bus session,
launches its own Xfwm and GTK application, bounds the child to 60 seconds and
records tagged process cleanup. It requires distro GTK3/Pango Python GI support;
no browser, network, credentials or user files are involved. Evidence is written
to a unique `artifacts/rtl/<time_ns>/` directory. Failure propagates as a nonzero
runner result rather than a successful partial report.

## Actual result

First attempt `1789874094012872612` passed all four scenarios on source base
`8c041d7`, fingerprint
`ffffeba5506af5c319fdcc86a0c82ec0bfcd07df8206fe9a8e96b95345290743`.
Source before/after matched and no tagged processes survived. Environment:
ordinary UID 1001, Ubuntu 24.04 ARM64, GTK `3.24.41-4ubuntu1.3`, Pango
`1.52.1+ds-1build1`, Xvfb `2:21.1.12-1ubuntu1.6`, Xfwm
`4.18.0-1build3`.

| Scenario | Independent observation |
|---|---|
| Exact mixed-direction replacement | Widget text and public readback matched `مرحبا שלום ABC 123 😀 نهاية` exactly in logical storage order. Widget direction was RTL. |
| Visual Left inside the Arabic run | Actual widget position changed from logical offset 2 to 3 while the strong cursor x-coordinate decreased from 164 to 156. Text was unchanged. Left moved visually left despite increasing the logical offset. |
| Visual Right from that position | Strong cursor x increased from 156 to 164, logical offset returned to 2, and text remained unchanged. |
| Logical selection and replacement | Public selection of code points 19–20 matched the widget's selected emoji range. Inserting `שָׁלוֹם42` replaced exactly that emoji; independently stored text and public full readback matched the expected concatenation, including combining marks. |

The oracle gets the widget's actual cursor position, converts its logical UTF-8
index using `Gtk.Entry.text_index_to_layout_index`, and reads Pango's strong and
weak cursor rectangles plus the entry's layout offset. Assertions compare the
measured geometry, not a guessed correspondence between logical offset and
visual direction. Application code only publishes state; it does not accept
external commands to mutate the widget. All changes and key input come from MCP.

## Limits

This establishes the distinction in one real GTK entry and one mixed-direction
sample. It does not qualify every bidi boundary, weak-versus-strong caret choice,
word navigation, multiline wrapping, selection highlighting, horizontal scrolling,
Unicode bidi controls, browser/provider behavior, or accessibility screen-reader
navigation. Movement checks deliberately use an unambiguous position within the
Arabic run; the final mixed selection reports both strong and weak coordinates
without pretending they are identical. Logical code-point offsets are not visual
columns or grapheme counts.

No driver defect or runtime change was indicated. This source-bound result is
local evidence for DATA-10; the catalog remains release-unqualified. The suite also has an optional `rtl` matrix registration, which retains its own
private-session launcher. Registration is not evidence of a current passing run.
