# Silo onboarding patch (configured source required)

These are Luda-owned integration assets for Silo commit
`777e1090d5e998059758160912138228ba98378d`. Nothing here pushes or modifies the
Silo repository automatically. The guest patch alone installs no software until
a caller adds its invocation; the subsequent desktop patch supplies that hook.
This is not a published Luda release or turnkey Mac onboarding.

## Source contract

The shipped `guest/agent-tools-release.json` is deliberately disabled. To enable
onboarding, the Silo integrator must supply and review a **trusted full source
archive**, not a wheel or an arbitrary moving branch. Example manifest structure
(the placeholders are intentionally invalid):

```json
{
  "schema_version": 1,
  "enabled": true,
  "source_url": "https://YOUR-TRUSTED-HOST/luda-PINNED-COMMIT.tar.gz",
  "source_sha256": "EXACT-64-LOWERCASE-HEX-ARCHIVE-SHA256",
  "source_commit": "EXACT-40-LOWERCASE-HEX-COMMIT"
}
```

Create the source artifact from a reviewed commit, for example using
`git archive --format=tar.gz --prefix=luda-COMMIT/ COMMIT`. Replace both occurrences
of `COMMIT` with that full commit identifier. Preserve the full tree, including
`requirements.lock`, `build-requirements.lock`, scripts, skills and package sources.
Record its SHA-256, serve those exact bytes over HTTPS, and put that URL, checksum
and commit in the manifest. This project does not currently supply a published
artifact URL. The archive digest pins bytes; the commit label is integrator-supplied
provenance, not cryptographic proof of a Git object relationship. Installation
executes trusted source/build code and can access package repositories using the
existing locked installer. It is not an offline installation.

URLs cannot contain credentials, query strings or fragments. Redirects must
remain HTTPS and satisfy the same rule. Download limits are 32 MiB and 120 wall-clock seconds enforced by a Linux process alarm covering headers and body; ordinary-file payloads are limited to 128 MiB across 10,000 yielded file/directory entries. Tar PAX/GNU metadata is parsed by Python before those counters and is not bounded by that payload limit.
Only ordinary files/directories under `luda-COMMIT/` are accepted, with no links,
traversal or duplicate paths. These are safety bounds, not a source trust sandbox.

## Lifecycle and state

The guest helper uses `/var/lib/silo-agent-tools` for a private operation lock,
atomic status and fresh per-attempt source/bundle directories. It installs to
`/opt/luda` for `silo-desktop` by importing and calling the verified source's
existing `bootstrap_guest.py`; there is no second installer or dependency solver.
It reads only `silo-desktop status`, never `connection`, and never starts or
restarts a desktop. A stopped/starting/failed desktop is pending until an explicit
start produces a running session. Bootstrap performs its own preflight again.

`ensure` installs only an absent/pending/unconfigured attempt. It neither
reinstalls on status polls nor automatically upgrades a successful installation.
A changed configured source reports `update_available`; a failed/ambiguous attempt
requires inspection and explicit `retry-after-review`. That action is a guest
administrative command, not an automatic timeout retry. Every retry uses a fresh
bundle directory. Retained attempt directories are not garbage-collected here.

Before invoking trusted source, the durable status sets `installation_completed`
to null and state to `unconfirmed`. The field describes the last bootstrap attempt,
not proof that no older installation exists. Bootstrap's own installer watchdog
and locks still apply. Abruptly killing this wrapper can leave descendants running;
the marker prevents automatic replay but does not prove process cleanup. Inspect
owned processes and selected release before an explicit retry.

The projected state contains no URL, arbitrary exception, path, viewer credential
or provider log. Bootstrap build output is discarded by this wrapper. `last_ready`
and `checked_at` describe a past bootstrap health check, not current availability;
a successful installation does not imply host Codex discovery. The private bundle
is under the corresponding `attempt-*/bundle/config`. No host profile, SSH key,
Codex registry or guest workspace skill path is modified by this integration.

## Apply and test

The checker requires the exact base and no tracked changes; it applies both patches atomically only with `--apply`. Supply a clean checkout of the pinned Silo commit:

```sh
python3 integrations/silo/apply.py /path/to/silo
python3 integrations/silo/apply.py /path/to/silo --apply
```

Canonical guest assets are also retained alongside the patch for review. Luda's
`tests/test_silo_integration.py` checks manifest validation, checksum/HTTPS policy,
archive restrictions, copied skill permissions, current manifest comparison, pending/start sequencing, durable interruption state,
no automatic retries/upgrades, sanitization and byte-identical patch application.
Run `python3 -m unittest discover -s tests -p test_silo_integration.py` from Luda.
Qualification fingerprints include `integrations/`.

These tests do not exercise a fresh microsandbox, packaged Mac app, actual source
server or host Codex placement. Those remain separate acceptance work. Configure
the artifact, verify the generated bundle in the intended remote executor/profile,
and exercise doctor plus an owned-file GUI task before claiming onboarding works.


## Silo hook and viewer patch

`0002-desktop-onboarding.patch` calls the wrapper inside
`desktop.rs::configure_with` after desktop setup/autostart. This path is synchronous
because new VM creation uses a temporary guest boot and expects the VM stopped
again afterward. The bounded guest operation allows 3900 seconds for desktop
setup plus onboarding. Optional setup commands run in their own `sh -eu` child;
ordinary setup failures do not fail the successful desktop operation.

An explicit ordinary desktop start/restart instead stages the helper/manifest
and dispatches `ensure` with detached stdin/stdout/stderr. The wrapper's existing
nonblocking operation lock prevents duplicate installation attempts. Dispatch is
not success: until a result is persisted, state is pending/unconfirmed. Bootstrap
owns its installer watchdog; VM termination or an outer kill can leave an
unconfirmed attempt. There is no global startup daemon and VM boot alone does not
run a pending tools installation. Explicit desktop start or desktop configuration
is the integration trigger. Stop never launches onboarding.

Running-desktop status adds a separate projected `agentTools` object. A failed
probe produces unconfirmed tools metadata without changing the desktop's state.
Stopped-VM status does not boot/probe the guest. The badge says **Last tools check
passed**, not that tools are currently ready or registered in Codex. Pending,
unconfigured and failure states still leave the native viewer attached. Fixed
reason codes distinguish unavailable desktop status and an operation in progress;
no raw exception is passed to the UI.

### Validation

Both patches applied cleanly in order to a pristine archive of the exact Silo
base. Twenty-one Python wrapper tests (as root and ordinary UID 1001) and eight qualification-fingerprint tests
passed. Eighteen focused Silo frontend tests and full TypeScript typecheck passed
using Node 24.21.0 and a private npm 11.6.2 installation; no global profile was
changed. Six focused `desktop::tests` also passed with Rust 1.94.0 on Linux ARM64. That unit build uses an explicit test-only `TAURI_CONFIG` override omitting bundled resources/external binaries; it does not validate resource preparation or package assembly. Exact final-pair results are recorded separately below.

Silo is not Mac-only: its Linux CI compiles the same desktop module on Ubuntu
24.04 AMD64/ARM64. `runtime-inputs.json` pins Rust 1.94.0. Native tests need GTK3,
WebKit2GTK4.1 and other native development packages plus explicit synthetic GitHub
build values; see `.github/workflows/linux-verification.yml` and Silo's release
guide. Packaged resource preparation is a separate step. Neither these tests nor
a native unit build proves Mac packaging, real fresh VM provisioning, host Codex
registration or user-profile discovery.


Final patch SHA-256 identifiers:

- `0001-guest-onboarding.patch`: `1546e65e10c2b645bfda896bb81fd9994d55198d25569defbca9f906b35fa04c`
- `0002-desktop-onboarding.patch`: `f4871fbafa5d58ef345cf583e25536596a573a9a42501f32c255867a8bc7b9e6`

The final helper changes tighten only Python metadata projection. The focused
frontend tests/typecheck exercised the byte-identical final `0002` patch.

The independent final-pair Rust run passed all six focused tests after a 9.93-second
incremental compile. Reverse-apply checks matched both final patches against the
tested checkout. Retained evidence is `artifacts/silo-rust/results.json` and
`cargo-desktop-tests.log` in the main Luda evidence directory; earlier successful
runs are retained separately. No microsandbox runtime was launched for that test.

## Explicit native host registration (third patch)

`0003-host-codex-registration.patch` adds **Connect tools to Codex** to the native
Desktop actions menu. The user selects an existing, owned canonical Codex profile
directory and trusted executable using explicit absolute paths, then confirms
registration for the displayed VM. No default profile is silently selected or
modified. This first action supports local Silo VMs only; remote Silo hosts are
refused. The Rust implementation requires no host Python runtime.

The native command reuses Silo's private pinned SSH transport, embeds the reviewed
Luda skill, and requires the installed guest skill to match those exact bytes.
Per-VM plugin, marketplace and MCP server identities coexist in one profile.
Persistent bundles and receipts live under the selected profile. A cooperative
profile lock serializes these registrations; it does not lock unrelated Codex
writers. Actual Codex CLI marketplace/plugin commands perform registration.
Readback verifies cached MCP/skill hashes and the effective stdio command, args,
environment, inherited environment names and working directory. Conflicting,
disabled, changed or interrupted registrations are preserved for explicit review;
this increment does not provide update/removal or automatically retry partial work.
Each CLI call is bounded to 30 seconds and 1 MiB output; timeout kills its process
group before returning an uncertain result. Error messages omit subprocess text.

The UI distinguishes registered profile configuration from runtime readiness.
Open a new Codex conversation, select the displayed VM-specific server and verify
`desktop_doctor`/`desktop_observe`. Identically named skill guidance is generic,
not a guarantee of VM routing. This action does not associate a plugin with an
undocumented Codex SSH executor, discover profiles automatically, or prove Mac
packaging or real microsandbox connectivity.

Validation: five native tests passed on Linux ARM64/Rust 1.94.0, including the
opt-in actual Codex 0.155.1 CLI test using temporary profiles. That test verifies
two distinct effective MCP servers, idempotency, preservation of unrelated model
settings, and refusal without overwrite of matching-argv overrides of `cwd`,
`env` and `env_vars`. Other tests cover unsafe/symlink profiles, lock contention,
partial registration without replay, and timeout cleanup preventing a late child
write. Twenty frontend tests and full TypeScript checking passed. Twenty-two Luda
integration tests passed, including exact embedded skill byte consistency. All
three patches applied to a clean checkout of the pinned base. The native unit
build uses the same test-only bundle-resource override documented above; it does
not qualify application packaging. Evidence lives in
`artifacts/silo-native-registration/` in the main checkout, including earlier
harness failures (incorrect synthetic build variable names and repeated fixture
directory creation), corrected logs and exact patch hashes.
