# Root installation with restrictive umask

The original installer reported `installed` and selected a release after root `umask 077` had created the prefix/release directories with mode `0700`. A real `runuser -u desktop -- test -x PREFIX` failed. The initial reproduction used the existing mocked build runner but real directory creation and selection; it did not claim an installed-wheel result.

The fix uses explicit permissions only for exclusively created directories and the new release payload. It does not change the process umask or chmod existing ancestors, source files or symlink targets. Existing-path traversal is tested with the selected account's UID/GID/groups before apt or build. Before selection, isolated installed Python must import server/session from its own virtual environment, see executable launcher paths, and read the skill. Reuse and rollback repeat this account check. No desktop session is needed and this does not claim MCP/GUI readiness.

The actual locked-wheel run in `tests/live_install_permissions.py` passed as root under `umask 077`, using an accessible dedicated `/workspace` parent and existing `desktop` UID 1001. The independent account probe matched **all 50 installed Python modules** and the bundled skill SHA-256 to the source. Retained [result](../tests/evidence/install-permissions/result.json) identifies release `0.1.0-8abe713d3a98e2b6` and exact installer source hashes; [compressed build log](../tests/evidence/install-permissions/install.log.gz) records locked dependency/wheel installation. Installer sources stayed unchanged during the run. Later evidence/document additions change the repository release identity; this result is scoped to the recorded build, not every later commit.

Eight focused regressions cover restrictive umask/new modes, source and external symlink-target preservation, unchanged existing prefix modes, failure before mutation, failure before selection/cleanup, reuse and rollback checks, actual inaccessible ancestor refusal as UID 1001, and rejecting a source import outside the installed virtual environment. The existing 35 installation/build/browser-selection tests passed with one optional build-dependency skip in the initial system-Python run. The fake-build unit fixture explicitly mocks account import/access proof; the real qualification does not.

Reproduce as root with existing `desktop`, provisioned Python/venv and normal package access, using fresh paths under an accessible parent:

```sh
python3 tests/live_install_permissions.py \
  --prefix /workspace/new-luda-permissions-prefix \
  --output /workspace/new-luda-permissions-evidence
```