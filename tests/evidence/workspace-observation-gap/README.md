# WM-08: explicit workspace switch leaves old screenshots usable

The catalog requires “Workspace switch: report active workspace and invalidate old observations.” At source `2818d80`, `InteractionMixin.switch_workspace` validates and dispatches `wmctrl -s`, then observes the requested active workspace. It never removes existing screenshots. `Desktop.signature` records each window's assigned workspace, geometry and active flag, but not the desktop's current workspace.

`probe.py` exercises the real switch and coordinate-validation methods with a deterministic fake WM/display. One sticky window remains active with unchanged native identity and geometry as workspace 0 becomes 1. The switch reports verified, while `_interaction_point` still accepts the pre-switch screenshot and returns coordinates. `before.json` retains this result. No graphical interface, real X11 request or input is involved. This establishes the runtime contract gap; it does not qualify actual WM behavior.

Small proposed correction: after validating the requested workspace, invalidate retained screenshot IDs immediately before dispatch. Do so even if the request later returns uncertain, since a switch may have occurred. An invalid argument should preserve snapshots because no input was sent. Existing `STALE_OBSERVATION` handling then directs the agent to observe again. No new tool, forced geometry, retry or implicit activation is needed.

Focused follow-up cases should cover verified switch, switch-away-and-back, unchanged requested workspace, dispatch failure after possible effect and invalid workspace before dispatch. A private actual sticky GTK window can independently establish active-workspace change while the old screenshot is refused before pointer input. External workspace changes are a separate boundary: they require sampling active-workspace metadata during observation/validation, and this minimal explicit-command invalidation would not claim to detect unseen change-and-return.

Run `.venv/bin/python tests/evidence/workspace-observation-gap/probe.py`. This audit does not change runtime or catalog qualification.
