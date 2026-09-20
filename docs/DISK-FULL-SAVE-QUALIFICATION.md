# Native editor save on full storage

`tests/live_disk_full_save.py` tests Mousepad against a real private 64 KiB tmpfs.
The final run observed FILE-06's exact acceptance criterion, **“Disk full: no
successful-save claim.”** It also discovered an application data-loss failure:
Mousepad truncated the existing document to zero bytes before displaying its
no-space error. This is retained as a failed preservation diagnostic, not renamed
a successful check or misrepresented as an additional catalog requirement.

The test deliberately returns nonzero while any assertion fails. The JSON field
`file06_no_successful_save_claim` separately reports whether both the visible
failure and dispatch-only tool response were observed. Neither that scoped field
nor this record changes release qualification.

## Run and isolation

From the checkout's locked-dependency environment:

```bash
sudo .venv/bin/python tests/live_disk_full_save.py --user desktop
```

The outer launcher requires mount capability and creates a new mount namespace
with private propagation before mounting its owned 64 KiB filesystem. The GUI
runner drops to the selected non-root account, creates private XDG directories
before D-Bus, and starts a private Xvfb/Xfwm desktop. It never fills the host disk
or mounts over an existing user path. Filling stops after at most 128 KiB of
attempted writes, with actual ENOSPC required. The desktop child is bounded to
90 seconds and tagged process cleanup records survivors. The namespace owner
unmounts its fixture in `finally`; namespace destruction also discards its mount.

Only public Desktop operations edit the buffer, dispatch Save, inspect the error,
dismiss it, read the retained buffer and approve the observed retry warning.
Filesystem reads independently check bytes and directory entries. No application
save implementation is patched. Output is saved outside the bounded filesystem,
under a unique `artifacts/disk-full-save/<time_ns>/` directory.

## Observed result

Source base `5ef173b`, test source fingerprint
`79690391c039cf85b06a4d7c4d002974b71070f0cf772e0863981b7a8f5d66f6`, run
`1789873930767430784`: **eight assertions passed, one preservation diagnostic
failed**. Source fingerprints before/after matched; no owned processes survived.
Versions: Mousepad `0.6.1-1build2`, Xvfb `2:21.1.12-1ubuntu1.6`, Xfwm4
`4.18.0-1build3`, Ubuntu ARM64, desktop UID 1001.

- Actual filesystem capacity was 65,536 bytes; filler reached 61,440 bytes before
  ENOSPC, alongside the original document.
- Ctrl+S returned `effect: dispatched` and explicitly said key delivery does not
  prove application outcome. The visible alert said “Failed to save the
  document.” and “Error writing to file: No space left on device.”
- The original 31-byte file became **zero bytes**. Only the document and owned
  filler remained; no recovery tempfile was observed. The empty-file SHA-256 was
  `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`.
- The error alert exposed no accessibility button. Escape dismissed the observed
  alert; the document remained open. Public text readback confirmed the full
  edited Unicode/emoji/tab/multiline buffer, and its title still marked it dirty.
- Removing only the owned filler made space available. A new explicit Ctrl+S
  opened an “externally modified” warning. The test inspected that warning and
  explicitly invoked its Save button, authorizing replacement of its own known
  truncated fixture file. Independent disk bytes then matched the entire edited
  buffer and the dirty title cleared. Only the document remained.

The exact catalog criterion has local evidence; safe preservation of original
bytes on ENOSPC does not. Agents must retain the visible failure and verify
recovery rather than treating dispatched Save or a dismissed dialog as success.
No Luda runtime change was indicated by this experiment.

## Preserved attempts and limits

All attempts remain in ignored artifacts. Run `1789873814413545312` stopped at a
fixture output-directory permission error; the launcher now prepares the helper's
import-time output directory. Run `1789873831692469820` first exposed the failed
original-byte assertion. Run `1789873860699563375` additionally measured zero bytes
but incorrectly searched for an absent Close button. Run `1789873884907734554`
confirmed retained edits but had not yet handled the retry's external-change
warning. Run `1789873906050776980` captured that actual warning and its actions.
The final fixture uses those observed UI decisions; no failure was turned into a
pass merely by rerunning it.

This is one editor/version on tmpfs, not universal atomic-save behavior, ext4
journal recovery, disk removal, quota exhaustion, OOM, or power-loss durability.
The buffer read and exact successful retry support retention in this scenario;
they do not promise recovery if the editor crashes after the failed save. The
standalone suite is not registered as a green CI gate: its failed preservation
diagnostic remains visible. See [helper/storage fault evidence](STORAGE-FAULT-QUALIFICATION.md)
for the separate startup and screenshot ENOSPC/EROFS checks.
