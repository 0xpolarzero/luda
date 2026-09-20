# Native save destinations

`tests/live_file_destinations.py` adds real Mousepad 0.6.1 workflows for FILE-10. Run it as an ordinary user in a private Xvfb/D-Bus/Xfwm4 session with private XDG directories created before D-Bus and `LUDA_ISOLATED_TEST_DISPLAY=1`. It reuses the editor driver in `live_file_workflows.py`: only public Desktop inspection, semantic input/actions and key methods drive the app. All paths belong to one temporary fixture directory; filesystem reads independently verify effects.

On Ubuntu 24.04 ARM64, UID 1001, Xvfb and Xfwm4:

- Save As to an existing relative symlink, followed by explicit Replace, preserved the symlink and wrote the exact Unicode/multiline value to its referent. The requested name was `visible-link.txt`; the actual resolved destination was `actual 日本語.txt`. The unrelated source retained its original bytes.
- An independent actor renamed the open file. Explicit Save As to its new name, followed by Replace, wrote the new path without recreating the old one.
- Editing again and saving used that new destination and preserved the old name's absence.

All three assertions passed. `artifacts/file-destinations/results.json` records the requested/resolved synthetic names and checks; `last-tree.json` retains the owned fixture's final inspected tree. The first harness invocation passed the assertions but its window-manager cleanup failed because that manager lacked its own process group. Its transcript was preserved; after fixing the harness process group, the complete run passed and tagged-process cleanup reported zero survivors.

This is application behavior, not filesystem confinement: saving through a symlink follows its target in this Mousepad version. Luda does not promise to prevent symlink substitution races or report a resolved filesystem path from a generic Save dispatch. Agents need application confirmation and a separate authorized filesystem oracle when the actual path matters. Arbitrary editors, concurrent symlink replacement, network mounts and automatic recovery of renamed documents remain unqualified. Existing overwrite cancellation and readonly-target cases remain in `live_file_workflows.py`.
