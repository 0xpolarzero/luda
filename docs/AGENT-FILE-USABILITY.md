# First-attempt native file-manager task

One fresh Codex agent completed a held-out Thunar task in **213.542 seconds** with
**75 public MCP calls**, **two tool errors**, and all seven independent filesystem
criteria satisfied. There was one attempt, a 300-second bound, no prompt tuning,
no menu coordinates or solution sequence, and no retry selection. This is scoped
local usability evidence, not comprehensive usability or release qualification.

The task opened a folder containing Inbox, Sorted, and References. The agent had
to move `旅程 東京.txt`, copy `Résumé été.txt` under the new name
`Résumé été — copie.txt`, preserve an existing same-name résumé in Sorted without
overwriting it, create a real symlink in References to the moved file, preserve
`À garder.txt`, and leave no extra files.

The agent independently found Thunar's **Make Link** action, moved and renamed the
result, and checked its Properties dialog. It used a temporary safe folder for
the résumé copy, renamed it, and moved it into Sorted without touching the existing
résumé. No drag-menu offsets from the preceding scripted fixture were supplied.

## Isolation and independent checks

[`scripts/agent_file_eval.py`](../scripts/agent_file_eval.py) reuses the existing
fresh-agent trace grader and ordinary-user desktop pattern. The existing root
Codex CLI authenticates normally; Thunar and Luda MCP run as UID 1001 in private
Xvfb/XFWM/D-Bus/XDG. The harness neither reads credential files nor changes global
configuration. The agent's temporary workspace contains only the installed skill.
Its exact CLI arguments, task, full events, stderr, versions, reported usage, and
source fingerprints are retained. The CLI uses `--ignore-user-config`, `--ephemeral`,
and `--sandbox read-only`, with approval configuration scoped to this synthetic run.

The independent filesystem oracle checks bytes, directory entries, the moved
file's inode, actual symlink type and resolution, and original file metadata.
A passive inotify watch also checks the protected destination inode for modify,
attribute, move, or deletion events, including overflow/error events as failures.
Timestamp checks alone proved insufficient in a preflight unit test: two writes
within one filesystem clock tick could produce identical metadata. The watch
caught that same-byte rewrite. No file operation in the task is performed by the
oracle; it only seeds the temporary files before the attempt and reads final state.

All seven checks passed, with **zero protected-file watch events**. Automated trace
grading and manual review found only the permitted skill `cat` command and public
Luda tools: no shell/file mutation, application-source access, terminal execution,
external navigation, or extra program launch. Five focused oracle tests cover the
initial failure state, correct result, same-byte overwrite, copy masquerading as a
symlink, and unexpected extra files.

## Friction retained in the result

The 75 calls comprised 26 key operations, 20 observations, 9 clicks, 8 inspections,
5 window lists, 3 semantic invocations, 2 text entries, one doctor, and one activation.
The agent initially searched the empty destination's Edit menu before discovering
Make Link on the selected source. That detour was recoverable exploration, but it
was not required by the final successful route. Two consecutive observations after
a rename also contributed to the call count.

Two failed calls are preserved verbatim in the trace and extracted error list:

- `FOCUS_CHANGED` when Properties was requested immediately after a rename-dialog
  confirmation, before the main window was active.
- `STALE_TARGET` when the agent subsequently inspected that closed rename dialog.

Post-hoc accounting of the unchanged trace, using
[`agent_trace_metrics.py`](../scripts/agent_trace_metrics.py), found **15,047 ms**
of summed public backend `elapsed_ms` across 73 calls. The two error responses
omit that field. This is not total tool wall time: the trace lacks event timestamps,
and the sum excludes transport, agent processing, and untimed errors. The remaining
wall time cannot be assigned to any one cause from this evidence.

The eight inspections returned **88,327 UTF-8 text bytes**. The initial unfiltered
inspection alone returned **57,450 bytes**, 123 nodes (79 showing, 80 unnamed), and
no accessible nodes named Inbox, Sorted, or References despite an untruncated tree.
It exposed the directory pane and navigation controls but not the icon-view folder
entries. That provides a concrete reason to use screenshots for folder navigation;
it does not establish that every returned semantic node was useless. Later narrow
menu/text filters produced useful one-node results of roughly 1.1 KB, and Properties
provided the actual symlink target.

Twenty observations returned **20 screenshots**, **1,146,502 decoded image bytes**
(**1,528,692 base64 characters**) and **32,136 UTF-8 metadata bytes**. Those byte counts
are not visual-token counts. Repeated context, screenshot processing, and tree size
may contribute to reported usage, but this single trace cannot isolate their costs.
The complete per-tool and per-inspection accounting is retained in the separate
`trace-metrics.json` sidecar; the first-attempt result and raw events remain untouched.

The agent recovered through a fresh observation and opened Properties successfully.
These errors did not mutate the wrong window or overwrite a protected file. A
future usability improvement could help agents wait explicitly for dialog closure;
this evaluation makes no runtime or skill changes and does not rerun the task.

## Reproduction record

Artifact directory:
`/workspace/luda-agent-files/artifacts/agent-files/run-1789875352352378003`.
The source fingerprint was unchanged during the attempt:
`bba7ce58cb9d470ff070d2f6b4b36c31e802e6de239f938588ce5c60f8f1e349`.

Versions: Codex CLI 0.155.1; Thunar 4.18.8-1build3; GTK 3.24.41-4ubuntu1.3;
AT-SPI 2.52.0-1build1; XFWM 4.18.0-1build3; Xvfb 21.1.12-1ubuntu1.6.
The CLI did not expose the resolved model in its JSON events; it remains **unknown**.
Returned usage was 1,868,922 input tokens, including 1,723,392 cached input tokens,
3,475 output tokens, and 91 reported reasoning-output tokens. These are the CLI's
reported totals, not a cost estimate or a claim that the task was efficient.

The evaluator is explicitly opt-in, outside default CI/matrix runs because it uses
authenticated agent service capacity:

```sh
.venv/bin/python scripts/agent_file_eval.py --backend-root "$PWD" --timeout 300
```

A future invocation is another recorded attempt, not permission to replace this
first-attempt evidence with a better result. GUI/theme/provider differences and
unknown default model resolution limit reproducibility and generalization.
