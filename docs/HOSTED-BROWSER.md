# Hosted owned-browser qualification

`.github/workflows/owned-browser.yml` separately tests the optional browser provider on Ubuntu 24.04. It first installs the default locked environment and asserts that Playwright is absent and browser capability remains unavailable. It then explicitly provisions the browser extra with `uv sync --locked --extra browser`, using uv 0.12.17, Playwright 1.63.0 and its Chromium revision 1243 (Chrome for Testing 153.0.8010.12). CI provisioning uses Playwright's installation command; Luda runtime never installs or downloads a browser.

The ordinary runner account executes the `owned-browser` qualification matrix in private Xvfb/D-Bus sessions. Chromium launches with its sandbox enabled. Ubuntu's downloaded-browser user-namespace restriction is addressed using an AppArmor attachment for the exact provisioned executable, following [Chromium's documented per-executable approach](https://chromium.googlesource.com/chromium/src/+/main/docs/security/apparmor-userns-restrictions.md). The job neither passes `--no-sandbox` nor disables the global user-namespace restriction. The CI-only attachment is removed afterward. This profile allows user namespaces; it is not a claim that AppArmor confines the browser itself.

`check_owned_browser_ci.py` refuses version/revision drift, a missing browser, root execution, and unsafe AppArmor attachment paths. Uploaded artifacts include the resolved versions, selected executable, generated attachment, source fingerprints, independent app oracles, and fixture logs. A missing dependency or failed fixture fails the job; no expected failures are converted into success. This job qualifies the owned-browser provider only, not arbitrary browser sessions, rich editors, macOS SSH routing or Linux provisioning.

Local validation used the same locked default/extra installation sequence: Playwright was absent by default, then installed as exactly 1.63.0. The checker accepted the already provisioned official ARM64 Chromium 153.0.8010.12 revision 1243. Matrix run `run-1789888248755165697` passed in 12.697 seconds as UID1001, with source unchanged and no remaining tagged processes. Local validation reused that existing browser binary; the fresh hosted download and AppArmor attachment still require the first GitHub run after integration. It does not claim AMD64 or hosted success in advance.

Actual hosted run [35496454208](https://github.com/0xpolarzero/luda/actions/runs/35496454208) passed at `f98b139` on ordinary UID1001/AMD64 Ubuntu: explicit locked provisioning, exact-executable AppArmor setup, sandbox-enabled Chromium and the 32.737-second matrix all passed. The source fingerprint matches the root/ordinary unit evidence in [the current record](../tests/evidence/historical-reports/UNIT-COVERAGE-CURRENT.md). The first workflow at `e78adab` failed before creating jobs because `runner.temp` was used in job-level environment configuration; the corrected workflow initializes the path in a runner step. Both outcomes remain recorded.

## Private document-portal teardown

Hosted run [35503837414](https://github.com/0xpolarzero/luda/actions/runs/35503837414)
at source76f9085 passed all51 rich-clipboard fixture checks and exited0, but the
matrix correctly failed cleanup with `ENOTCONN` while removing its private
`runtime/doc`. The private D-Bus session had activated xdg-document-portal;
a disconnected FUSE mount remained after process teardown. The other five
browser suites passed. This was neither a browser assertion failure nor the
previous aggregate suite timeout; no operation deadline is increased.

The matrix now reads mountinfo before directory removal. It detaches only the
exact `runtime/doc` `fuse.portal` mount inside its fresh current-UID0700 root and
runtime directory, requiring the mount's user_id to match and its mount record
to remain unchanged. `fusermount3` is an explicit CI dependency. Mount-table
removal must be observed before recursive deletion. Unexpected, foreign or
unconfirmed mounts preserve the directory and fail cleanup; the original fixture
verdict is retained separately. This does not authorize unmounting ordinary user
portals or unrelated mount points.

An actual ordinary-UID caller test in fresh user/mount namespaces creates a FUSE
mount, closes its connection, reproduces the original `rmtree` ENOTCONN, then
verifies scoped detach/removal and preservation of an unrelated sibling. The
namespace maps that caller to UID0 for the mount syscall; it is not a hosted
normal-namespace rerun. Run `tests/live_private_portal_cleanup.py` as an ordinary
user with Linux unshare, /dev/fuse and fusermount3 available. Focused unit tests
cover foreign/type/path/mount-record changes, failed unmounts, permissions,
symlinks and separate fixture/cleanup outcomes. Original hosted failure evidence
and local proof are retained in `tests/evidence/hosted-portal-cleanup/`.
