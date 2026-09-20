# Explicit Silo guest bootstrap

From an existing Silo guest with its desktop running, use a trusted local Luda
checkout and a fresh output path beneath a directory you own:

```sh
sudo python3 /absolute/luda/scripts/bootstrap_guest.py \
  --source /absolute/luda \
  --prefix /opt/luda \
  --user silo-desktop \
  --output /root/luda-onboarding-1
```

This single command checks Silo's nonsecret `status`, installs a versioned Luda
release, runs the existing session-aware doctor and generates a remote-placement
configuration/skill bundle. It does not start or restart the desktop. It does not
register a plugin, edit Codex settings, configure SSH, read viewer credentials or
change Silo itself. Source must be supplied locally and trusted: installation
executes its build and installer code. Use the same source revision for the
bootstrap and installed release.

All path/account/output validation and Silo status preflight precede installation. Source, prefix and output must not overlap in either direction. Non-root system provisioning is rejected before child execution; use `--skip-system` only for already provisioned dependencies.
The current helper must report installed desktop version `1`, the exact selected
non-root account and `running`. Unknown/missing/incompatible status fails before
installation. Start a stopped desktop explicitly in Silo, then retry. For a
root-owned prefix, run management as root; the existing session launcher drops
to the desktop account before GUI access. A preprovisioned environment can append
`--skip-system`, which passes through to the existing installer. No second
installation implementation or dependency resolver is introduced.

## Results and retries

Stdout is one JSON result; installer progress goes to stderr. That stderr is explicitly trusted source/build output and is not redacted by the wrapper. JSON projection privacy does not promise privacy for arbitrary build logs. Arbitrary status
fields, provider stdout and exception text are not copied into the JSON error.
The response reports `stage`, `installation_completed`, `codex_settings_modified`,
`configuration_generated`, projected desktop state and, after successful
installation, the selected release. The fresh output directory is created with
mode 0700 and existing output is never overwritten.

- A validation/preflight failure performs no installation and does not reserve
  the output directory.
- An installation failure uses the existing installer's preservation rules.
  Inspect its stderr and selected release before retrying; interrupted installs
  are handled by that installer.
- A later readiness or configuration failure reports installation completed.
  The newly selected release remains installed; bootstrap does not silently
  roll back. Resolve the reported stage and rerun with a fresh output directory.
  The installer reuses matching verified releases.

On success, `config_directory` names `<output>/config`, containing
`config.toml.fragment`, `.agents/skills/luda/SKILL.md` and placement instructions.
After the installer exits, bootstrap acquires the existing prefix lock, requires the selected release to match the supplied source identity, and holds that lock through doctor and configuration generation. It never holds the lock while invoking the installer. A competing managed release switch is refused or serialized; later intentional updates can still change the generated `current` launcher. Successful readiness is a point-in-time check, not permanent session availability.
No successful result asserts host discovery or release qualification.

Interrupted child execution is cleaned using a per-invocation inherited token and revalidated process UID/start identities, including children that create new sessions. This targets only tagged descendants, not other installer processes or global process names. Cleanup is bounded; the contract assumes the trusted installer descendants preserve the inherited token. A timeout/interruption reports installation outcome `unknown` and disallows automatic retry, even if tagged cleanup succeeds: inspect the selected release and retained output first. If cleanup cannot be proved, `cleanup_verified` is false. Abrupt termination of bootstrap itself is not a durable external process supervisor.

## Finish in the intended host context

Transfer the reviewable configuration bundle through your existing connection
when needed. Merge its MCP table into the **host Codex profile/project that owns
the selected remote executor**, preserving unrelated entries. The fragment uses
`experimental_environment = "remote"`; command paths remain Linux guest paths.
It does not create an SSH connection. Place the skill in the intended guest
workspace or agent skill scope, then independently verify its discovery in a
fresh remote task. If using the separate plugin workflow, register a matching
remote bundle in the intended host profile instead of registering duplicate
servers through both mechanisms. See [installation](INSTALLATION.md) and
[plugin placement](CODEX-PLUGIN.md).

Verify `desktop_doctor`, the Luda skill and a screenshot of the intended guest,
then perform an owned-file UI task with independent readback. Actual Mac/Silo
placement and discovery remain unqualified. Automatic invocation from Silo GUI
installation/upgrades, host registration and separate tool health UI still need
Silo integration changes; this explicit guest bootstrap is not that adapter's
host half. [The Silo source review](SILO-INTEGRATION-REVIEW.md) identifies the
actual integration points.

## Validation scope

Twelve focused tests cover rejection before child execution, stopped/missing
status ordering, literal shell-looking paths as argv, installer output routing,
install/readiness/config failure boundaries, selected-release preservation,
status/error redaction and machine-readable CLI failure, all path overlaps, non-root provisioning, release switching, and lock coverage. A real detached-child timeout regression verifies the tagged child cannot produce a delayed file effect. Existing installer tests
remain separate. Actual installed-guest composition is intentionally deferred to
the integrated source run under `/tmp/luda-live-tests.lock`; these unit tests do
not claim it passed.
