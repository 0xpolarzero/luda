# Managed desktop wrapper cleanup

Hosted owned-browser run [35506123999](https://github.com/0xpolarzero/luda/actions/runs/35506123999), source `d193`, failed in `tests/evidence/managed-browser/run.py` temporary-directory cleanup with `ConnectionAbortedError` (errno 103) at `/tmp/ld-test-wfy6t8sa/run/doc`. The original log is retained unedited/compressed. It did not retain a mount-table snapshot; attribution to the document-portal mount family is supported by the location/error and prior disconnected-mount evidence, not proof of that historical mount's exact record. No fixture assertion is relabeled a cleanup success.

The managed wrapper now reuses `scripts/private_directory_cleanup.py`, with its exact same-owned-UID/0700 root, `runtime/doc`, `fuse.portal`, mount-record identity and post-detach verification constraints. It uses `runtime` instead of `run` and keeps the short `ld-test-` prefix to avoid long Unix socket paths. Only an optional context-manager prefix parameter was added; mount matching was not broadened. Unknown mounts, missing utilities, changed ownership and unconfirmed detach remain failures and preserve the directory. `private-directory-cleanup.json` retains the probe's verdict separately from cleanup, including when a passed probe is followed by failed cleanup.

Ten focused tests passed (eight existing cleanup cases and two managed-wrapper integration cases). The latter replace only the spawned probe to verify environment layout, failure exit preservation, and cleanup-failure propagation/receipt. Run:

```sh
PYTHONPATH=tests .venv/bin/python -m unittest test_managed_private_cleanup test_private_directory_cleanup
```

The actual cleanup proof runs the managed wrapper with a test-double GUI child that mounts and disconnects a **real** `fuse.portal` endpoint at the wrapper's chosen path. Its real cleanup calls the real extracted `fusermount3`; the final proof confirms one mount detached, directory and mount absent, and an unrelated marker preserved. Caller UID 1001 enters private user/mount namespaces mapping only itself to namespace UID0. The runner's root-GUI guard is overridden only in this test because the GUI child is mocked; the helper validates actual namespace ownership unchanged. No real GUI, installed release or shared mount is involved. This is a cleanup integration test, not managed-browser release acceptance.

The first attempt used `unshare --map-current-user`; this kernel refused the raw FUSE mount with EPERM before the endpoint existed. Mapping that same caller to namespace root worked, as in the pre-existing isolated FUSE proof. Two subsequent actual runs passed; the final stdout and exact runtime/helper/test hashes are retained as `private-proof.jsonl` and `source.json`.

```sh
runuser -u silo-desktop -- env PATH=/path/to/extracted/fuse3/bin:/usr/bin:/bin \
  .venv/bin/python tests/live_managed_portal_cleanup.py
```

Requires Linux user/mount namespaces, `/dev/fuse` and `fusermount3`. Here the existing test-only official Ubuntu `fuse3_3.14.0-5build1_arm64.deb` was extracted without installation/postinst; package SHA256 `133c0e1c1fd0ce655b8f15c693f3ee6d2aeb22b2675512ccc6bef82de8a88d09`. Hosted browser CI already explicitly provisions fuse3. No new runtime dependency or production cleanup policy is introduced.

At integrated source `f515806`, the revised runner also passed a real ordinary-account private Xvfb/D-Bus browser workflow against existing installed release `0.1.0-2d841f3b6d26f20e`: independent Unicode content matched, owned-browser EOF cleanup completed, and the private directory was removed. No portal mount needed detachment in that run. The `actual-installed-*.gz` receipts qualify the revised runner against that existing release, not a newly installed source package. The separate disconnected-FUSE proof above exercises the mount-detachment branch.
