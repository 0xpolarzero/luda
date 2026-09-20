# Optional browser tools in a managed installation

Browser support is an explicit installation choice. The default installer remains
browser-free. Supply an existing trusted Chromium distribution; Luda neither
fetches it nor runs `playwright install`, modifies browser sandbox policy, disables
the sandbox, or deletes that external distribution.

Create a JSON selection file readable by the installer, owned by its account or
root and not group/world writable. Example (replace the illustrative hash with
the independently verified expected digest, not a value guessed from this guide):

```json
{
  "schema_version": 1,
  "executable": "/opt/trusted-chromium/chrome",
  "sha256": "EXPECTED_64_LOWERCASE_HEX_DIGEST",
  "version": "153.0.8010.12",
  "architecture": "aarch64"
}
```

Supported architecture values are `aarch64` and `x86_64`, matching the current Linux
host and ELF machine. The executable must be a canonical absolute path, an
executable regular ELF64 file of at most 1GiB, without writable group/other bits. Shell wrappers
and symlink paths are deliberately unsupported. The hash covers **only the
executable file**, not adjacent resources/libraries or the entire distribution.
Provision those files from your separately verified artifact or package source.
The installer probes the exact version with bounded output/time after checking
the hash. When invoked as root it runs that probe as the explicitly selected
ordinary `--user` account, never root. That account needs access to the selected
browser and its resources.

```sh
bash scripts/install.sh /opt/luda --browser-config /absolute/browser.json --user desktop
# Existing system dependencies may be explicitly reused:
python3 scripts/manage_install.py install --prefix /opt/luda \
  --browser-config /absolute/browser.json --user desktop
```

The browser-enabled release installs `requirements-browser.lock` with hash checking;
that export includes the default dependencies plus the pinned browser extra.
The default release still installs `requirements.lock`. Browser options contribute
to release identity, so base/browser selections and changed versions are distinct
installations. A failed preparation leaves the previous selection intact.

Each browser-enabled release stores `.venv/luda-browser.json`. `luda-session`
revalidates that fixed selection **after switching to the desktop account**, then
passes only its executable and verification metadata to the launched command.
Before every owned-browser open, the backend revalidates the expected selection again; changed files refuse with no dispatched input. Hashing uses nonblocking/nofollow regular-file descriptors, bounded chunks, a five-second deadline, operation cancellation checks and before/after file identity checks. Hash deadline/cancellation checks are cooperative between reads; they do not guarantee interruption of a kernel-blocked remote-filesystem read. This is not protection against a hostile same-account actor racing arbitrary changes after verification, nor does it hash adjacent browser resources.

Ambient `LUDA_CHROMIUM_EXECUTABLE` is still discarded. Existing managed MCP/SSH
command paths remain unchanged. Doctor reports the Playwright version and verified
executable version separately from `launch_verified: false`: dependency/version
checks do not establish sandbox, display or application launch success. Doctor labels the verification as historical launcher-startup evidence; it does not assert that the file has remained unchanged since then. Missing Playwright distribution metadata makes the optional capability unavailable without breaking core diagnostics. Explicit
`desktop_open_browser` reports the version of the actual launched browser.

Rollback verifies the old release and its external executable before selecting it;
a removed, changed, incompatible or inaccessible browser refuses rather than
pretending browser readiness. Disabling uses a separate default installation or
rollback to a browser-free release. It never edits an existing release in place.
Running MCP processes are not killed or upgraded automatically; reconnect a fresh
conversation to use the selected release. External browser resources are not owned
by Luda, and rollback cannot restore them. Keep versioned trusted distributions
available while releases reference them.

Tests include schema/permission/hash/version refusal, a bounded rapid-output probe,
timeout and successful-parent background-child cleanup, distinct release identity,
idempotency, failure preservation, rollback refusal, and post-UID-drop handoff.
`tests/evidence/managed-browser/` exercises a real installed wheel through the
managed launcher and public MCP on an ordinary-account private XFCE/Xvfb desktop,
with an independent HTTP text oracle. It does not establish Linux UI or macOS
provisioning readiness.
