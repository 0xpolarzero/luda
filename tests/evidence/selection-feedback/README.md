# Selection feedback: fresh-agent evidence

2026-09-21, Ubuntu 24.04 ARM64, existing authenticated Codex CLI 0.155.1.
No model override was supplied; the CLI JSON did not expose the resolved model.
Each attempt used a fresh ephemeral agent, copied complete skill, private workspace,
and ordinary `ubuntu` desktop/MCP account with private Xvfb, D-Bus and profile.
The harness did not read or copy credentials; the CLI reused its existing authentication. No shared desktop or system packages changed.
Budget: 180 seconds per attempt. All eight attempts are retained in `runs.json`.
This is a small observed sample, not a reliability estimate.

Tool correctness was checked separately: 1,068 unit tests ran successfully with two environment skips, and the three wheel-build tests passed separately. The real XFCE regression confirmed that both changed and already-selected results carry selection-only feedback, both leave the actual theme setting unchanged, and advertised activation applies it. Existing result fields and selection behavior are preserved; failures and uncertain results do not acquire verified-selection guidance.

| Attempt | Seconds | Independent outcome | Agent's final assessment |
|---|---:|---|---|
| baseline | 110.68 | Greybird-dark | Could not verify visually; setup omitted xfsettingsd, not comparable |
| baseline2 | 110.88 | Greybird-dark | Applied and verified |
| baseline3 | 147.31 | Greybird-dark | Applied and verified |
| fixed1 | 105.45 | Greybird-dark | Could not verify visually |
| fixed2 | 134.75 | Greybird-dark | Could not verify visually |
| fixed3 | 94.29 | Greybird-dark | Applied and verified |
| file1 | 42.95 | No open; selection oracle unavailable in icon view | Claimed selected/unopened; selection not graded |
| file2 | 24.09 | Initially unselected, finally selected, never opened | Correctly reported selected/unopened |

Baseline2/3 and fixed1/2/3 used the identical prompt, desktop setup, model default
and budget. The reported false-completion failure **was not reproduced** in the
two comparable baseline trials. All three fixed agents received the new
`verification_scope: selection` and conditional `next_step`, then used an
advertised activation action. All three independently ended with
`/Net/ThemeName=Greybird-dark`, but only one claimed verified completion; two
honestly reported that the Appearance window still looked light. This validates
actual state changes, not universal agent verification success or a demonstrated
improvement over baseline. The visual discrepancy's cause was not established.

The theme oracle polls `xfconf-query -c xsettings -p /Net/ThemeName` outside the
agent's tools. It does not use row selection as proof of applying a theme.
Baseline1 omitted xfsettingsd; all later theme attempts include it. GTK's
`CssProvider.get_named` returned distinct CSS digests for Greybird,
Greybird-dark and Adwaita under the supplied asset paths, confirming that GTK
could load the theme assets. This does not explain the visual discrepancy.

File1 was retained as oracle-limited, not scored as a pass or an agent failure:
Thunar's icon view did not expose the filename to the independent AT-SPI query.
File2 starts Thunar in details view, requires an independently observable,
unselected file before starting the agent, and clears accessibility caches.
Its independent AT-SPI oracle observed the final selected state. A private MIME
handler records any file open; its operation was preflight-tested before the
agent and the marker reset. No open occurred. The agent used `desktop_choose`
once and did not activate the file. The task wording was unchanged.

`runs.json` includes exact prompts, final messages, original tool feedback,
selection/activation calls, independent state, source commits and hashes, and
trace grading. Hashes labeled retrospective were collected from the recorded
Git commit after the runs; they are not runtime attestations. Baseline harness
formatting/diagnostic additions happened while some baseline processes were
already loaded; product code and copied skill stayed unchanged. Fixed theme
runs used a frozen harness. Its subsequent hardening adds explicit account and
private-child guards, atomic oracle writes and separate oracle/trace grading.
No agent was coached with an expected action sequence or oracle details.
The allowed public tools include legitimate application launches; the inherited
range-test `no_injected_actions` flag is not used to reject ordinary launches.

Baseline product commit: `adba0834504d22e42e97a68e87c7f61759d18aba`.
Fixed product commit in the trial worktree: `069f6f8` (cherry-picked runtime
`535a171`, skill `386c02e`, version `a72f58d`). The editable package's installed
metadata still reported 0.3.2, while source hashes and new feedback show the
candidate implementation was executed. Raw CLI events and desktop logs remain
under `artifacts/agent-selection-effect/<attempt>/` (not checked into Git).

Themes were downloaded and extracted, not installed:
https://ports.ubuntu.com/ubuntu-ports/pool/universe/g/greybird-gtk-theme/greybird-gtk-theme_3.23.3-1_all.deb
SHA-256: `229bd6c832963109d4fd58d3d8f662b94d461c413f48c81ad7d18350c57d922e`.

Reproduce with an existing authenticated Codex CLI and the extracted package:

```sh
.venv/bin/python scripts/agent_selection_effect_eval.py \
  --user TEST_ACCOUNT --themes /absolute/extracted/usr/share --label theme
.venv/bin/python scripts/agent_selection_effect_eval.py \
  --user TEST_ACCOUNT --themes /absolute/extracted/usr/share --task file --label file
```

The harness runs from root solely to reuse existing CLI authentication while
running the desktop and MCP server as the explicitly named ordinary account.
Missing authentication or desktop prerequisites are blockers, not simulated
agent passes. Core regression tests separately cover both changed and already
selected feedback; these fresh-agent samples exercised changed selection.
