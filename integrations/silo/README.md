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
and commit in the manifest. A [verified full-commit GitHub archive candidate](releases/fd2da8e.json) is
already available; see the [source proof](../../tests/evidence/source-archive/README.md).
The canonical default manifest remains disabled pending integration selection. The archive digest pins bytes; the commit label is integrator-supplied
provenance, not cryptographic proof of a Git object relationship. Installation
executes trusted source/build code and can access package repositories using the
existing locked installer. It is not an offline installation.

The [release artifact helper](../../docs/RELEASE-ARTIFACT.md) can now prepare a
candidate archive, checksum, manifest and Git-tree provenance together. It checks
every archived file against the exact commit, disables replacement objects and
preserves existing output directories. It does not publish the asset or enable
this integration's manifest.

URLs cannot contain credentials, query strings or fragments. Redirects must
remain HTTPS and satisfy the same rule. Download limits are 32 MiB and 120 wall-clock seconds enforced by a Linux process alarm covering headers and body; the entire decompressed tar stream (including PAX/GNU metadata, headers, padding and concatenated gzip members) is limited to 128 MiB before tar parsing. Expansion uses bounded reads into an anonymous disk spool in the owned staging parent; it is closed on success or failure. Parser reads/seeks are constrained to that validated stream, including malformed oversized declared metadata lengths. The separate 128 MiB ordinary-file payload and 10,000 yielded file/directory entry limits remain; header overhead means the effective payload allowance is smaller than 128 MiB. Invalid gzip CRC/footer, malformed tar and spool disk failures produce a fixed source-preparation error. These are byte/entry bounds, not a guarantee of atomic metadata-parser CPU time.
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

### Registration transport preservation fix (fourth patch)

`0004-preserve-registered-transport.patch` fixes a lifecycle ordering bug in the
third patch: preparing transport directly at its persistent location could replace
SSH config/host pins before a renamed VM's bundle conflict was refused. The fixed
path prepares a disposable candidate, rendering its known-hosts reference for the
final location. It compares both files against existing transport and validates
the bundle before publishing a first transport directory. Registration never
replaces existing transport files, even when later CLI verification refuses.
Changed aliases, pins, manually edited config and bundle conflicts preserve the
old bytes. Candidate preparation still uses the existing editor identity/key
provisioning mechanism; this is not a claim of zero side effects across Silo's
identity store. Six native tests passed including the actual CLI test and the
new regression for all four preservation cases. Apply all four patches in order;
the first three remain byte-identical to their previously tested versions.

## Bundled skill alignment

`0005-refresh-agent-skill.patch` updates the native registration bundle with the optional OCR guidance. Earlier patches remain immutable; the applied series must embed the exact current reviewed skill. The integration test applies every ordered patch to the skill path and compares final bytes. Native registration still refuses a guest with a different installed skill instead of pairing mismatched guidance silently.
### Native discovery, Browse and explicit Disconnect (sixth patch)

`0006-host-registration-lifecycle.patch` adds file/folder Browse dialogs and a
read-only **Find installed Codex** action. Discovery checks owned executables in
PATH and common installation directories, plus existing CODEX_HOME and ~/.codex
profile directories. It executes no candidate program and fills only blank fields;
the selected paths remain visible for review. Missing app-bundled CLIs can be
selected with Browse. Canceling a picker preserves the existing entry. Neither
selection nor discovery registers anything.

**Disconnect from this profile** is an explicit action scoped to the displayed VM
and profile. It requires a matching owned receipt, cached files and effective
transport before invoking `codex plugin remove`. It verifies both the installed
plugin entry and resolved server are absent before claiming profile removal.
Unrelated plugins/settings and marketplace registration remain untouched. Persistent
bundle and transport files remain available to running clients; the action does
not terminate existing MCP processes or claim their shutdown. The Codex CLI itself
removes its plugin cache. Failed/uncertain removal is recorded durably and never
retried automatically. Repeating removal after confirmed absence is read-only
apart from receipt refresh. Changed/disabled registrations require review. After confirmed removal, a new explicit Register action reconnects the same
verified bundle only if its identity is unchanged and no server occupies its name.
Unconfirmed removal and changed bundle identities still require review; changed
version updates remain a subsequent increment.

Seven native tests passed, including two opt-in actual Codex CLI tests: selected
VM removal leaves the other VM and unrelated settings, repeated removal verifies
absence, explicit same-bundle reconnect is verified, overridden transports are refused, and a synthetic failed remove leaves
the installed server while preventing a second mutation. Twenty-three frontend
tests and TypeScript checking passed, including picker cancellation, explicit
Disconnect, and discovery preserving a typed profile without registration. The
sixth patch applied cleanly after the first four (the fifth refreshes only skill
bytes). This remains Linux qualification of native logic, not macOS dialog or
packaging acceptance. Logs are in `artifacts/silo-native-registration/`.

### Reviewed same-transport version update (seventh patch)

`0007-reviewed-version-update.patch` adds **Review update**, followed by a separate
**Confirm this update**. Preview reads the selected profile and installed guest
skill without changing the registration. It shows the VM/profile, old/new versions
and skill hashes. The guest skill must exactly match the reviewed skill embedded
in this Silo build. A profile lock coordinates Silo operations; it is not a global
lock on independent Codex writers.

Confirmation recomputes a digest covering the selected executable identity,
profile/VM, receipt, source catalog/manifest, cached manifest/skill/MCP contents,
effective server configuration, current SSH config/pins and proposed new version.
A stale preview refuses without applying. Modified or disabled registrations,
changed marketplace sources/catalog paths, modified cache files and changed SSH
aliases/pins are refused. This increment updates the reviewed skill/version while
keeping the exact MCP command and SSH transport; changing transport requires a
separate deliberate migration and is not silently incorporated.

Codex 0.155.1 has no `plugin update` command. An actual isolated CLI probe confirms
that `plugin add PLUGIN@MARKETPLACE` installs a changed local version in place.
After confirmation, Silo records an uncertain update receipt, archives the old
reviewed source bundle, publishes the candidate and issues **one** plugin-add
operation. Fresh CLI/cache readback establishes the new version even if the add
acknowledgement is lost. Failure preserves the uncertain receipt, old source
archive and SSH transport; there is no automatic retry, rollback or remove/re-add.
Existing clients are not killed. Codex itself removes the previous version's
cache, so the UI tells users to start a new conversation and does not promise
old cached skill paths remain available. The editor's public-key derivation used
by read-only transport checks now has a five-second subprocess deadline.

Validation on Linux ARM64: eight native registration tests passed, including three
actual Codex CLI cases. The update case verifies source/config preservation during
preview, stale-plan refusal, changed source/catalog/cache and disabled-state
refusal, lost-response reconciliation, new cached skill bytes, unchanged server
namespace, the other VM remaining registered, and failed-install uncertainty with
no replay. A separate native transport test verifies config/pin mismatches are
read-only. Twenty-four frontend tests and TypeScript checking passed, including
the separate confirmation and preview invalidation on profile edits. The patch
applies after the previously qualified native patches; skill-refresh patch five
changes only embedded bytes. Evidence is in `artifacts/silo-native-registration/`.
The actual native key-derivation/SSH path was not run in this VM, which lacks
`/usr/bin/ssh-keygen` and `/usr/bin/ssh`; native compilation, pure transport checks
and real temporary-profile Codex behavior are distinct from macOS/real-VM acceptance.

### Actual native SSH helper qualification (eighth patch)

`0008-native-ssh-qualification.patch` closes the unexecuted native SSH/key-derivation
path noted above. Eight editor/helper tests passed using official Ubuntu OpenSSH
9.6p1-3ubuntu13.19 ARM64 and OpenSSL 3.0.13. The real-VM editor test remains explicitly
ignored. Previously extracted distro binaries were temporarily exposed at the
otherwise absent `/usr/bin/ssh` and `/usr/bin/ssh-keygen`; those exact test-owned
symlinks were removed afterward. No package post-install script, SSH server,
service, global SSH configuration or existing credentials were involved.

The new actual test generates disposable client/host keys, renders private pinned
config under paths containing spaces, both quote characters, percent signs and
literal `$(touch INJECTED)`, and checks `ssh -G` HostName, root user, identity and
known-host paths plus strict pinning/forwarding settings. A deliberately failing
owned proxy records exact argv/environment through a real SSH invocation; the
metacharacters stay literal and no injection marker appears. This does not launch
microsandbox or establish a remote session. Public-key derivation and read-only
verification preserve config/pin/key bytes and modification times. Replacing the
owned host key under the same alias is refused without rewriting the old pins.

A private dependency seam tests key-derivation timeout and output overflow without
adding a production executable override. Production remains the fixed system
ssh-keygen with a five-second deadline; accepted output is limited to 4096 bytes, and timeout
or overflow terminates the owned process group before returning. The timeout test
proves a delayed child marker is never written. Existing SSH config preservation,
public-key parsing, quoting and file-mode/symlink tests also pass. Exact logs,
binary versions/hashes and cleanup evidence are in
`artifacts/silo-native-registration/native-ssh.json`. This closes Linux native
helper execution, not real Silo routing or macOS application acceptance.

### Bounded pipe capture and unconditional keygen cleanup (ninth patch)

`0009-bound-keygen-capture.patch` corrects two limitations in patch eight's capture:
file-size polling was an acceptance check, not a hard disk-write bound, and a
successful direct child could leave a descendant running. Capture now uses a
nonblocking pipe and a user-space buffer of at most 4097 bytes (one byte detects
exceeding the 4096-byte acceptance limit). Kernel pipe capacity provides bounded
backpressure; no output file is created. This does not claim the child cannot
write more than 4096 bytes into the pipe before termination. An ownership guard
terminates the whole process group and reaps the direct child on every exit path,
including successful status, parse/I/O failure, overflow and timeout.

Nine editor/helper tests pass with the same actual OpenSSH binaries; one real-VM
test remains explicitly ignored. New cases run a rapid 64 MiB output command and
successful/failed parents with background children scheduled to write late
markers. Overflow is refused promptly, and no marker appears after cleanup.
Actual native key generation, SSH parsing and literal proxy arguments still pass.
The temporary binary symlinks were again removed afterward. Evidence is
`artifacts/silo-native-registration/keygen-pipe.json` and its captured test log.

### Inspect and reconcile interrupted updates (eleventh patch)

`0011-inspect-update-recovery.patch` adds **Inspect interrupted update**, then a
separate token-bound **Finish verified update** or **Keep previous version**.
Inspection distinguishes installed-cache/effective-configuration proof from live
SSH connectivity. It never installs/removes a plugin, publishes files, or changes
the registration receipt. Confirmation reconstructs the owned source bundle to
match the version that Codex has already installed, then verifies normal CLI state
before reconciling the receipt. There is no installation replay or automatic
rollback, and existing processes are not restarted.

This closes four durable dead ends: old source still intact before publication;
old source archived but replacement publication failed; new source published with
the previous cache still installed; and the updated cache installed but the caller
or verification reply lost. Actual Codex 0.155.1 refuses ordinary plugin/marketplace
listing when a configured source root is missing. Recovery verifies the selected
profile's owned local source using bounded TOML parsing, then uses Codex's documented
per-invocation `-c marketplaces.NAME.source=VERIFIED_ARCHIVE` override for read-only
listing. The configured source is never edited. This reports the installed cache
version even when the retained source manifest describes the previous version.
The parser reuses already locked TOML 0.9.12; Cargo.lock changes only Silo's direct
dependency reference.

Inspection validates receipt identities, owned archive paths, source/cache hashes,
manifest/catalog fields, the effective server and current native SSH pins/config.
A digest binds these observations and the selected executable/profile/VM. A stale
confirmation refuses. Disabled/removed registrations, another installed version,
changed marketplace source, cache corruption and independent MCP overrides produce
sanitized, actionable conflicts without overwriting another choice. Source/candidate
archives are retained through publication and receipt failures. Interrupted recovery
can itself be inspected and completed. The bounded archive list permits up to 16
retained recovery-source references before requiring review; no archive is silently
deleted to make room.

Validation: nine native registration tests passed, including four actual CLI tests;
the final recovery case was rerun after adding a concurrent-writer case and a
first-rename-success/second-publication-failure assertion. It covers all four update
states, a SIGKILLed owned wrapper after real CLI installation, receipt persistence,
stale confirmation, missing source, independent source/transport/disable conflicts,
publication and receipt-write failures, and later successful recovery. Recovery's
CLI test seam rejects every plugin-add/remove request. Another VM, selected profile
configuration, old sources and SSH pins remain preserved. Twenty-six frontend tests
and TypeScript checking pass, including inspection before either explicit action
and the distinction from SSH readiness. Initial implementation's TOML parsing failure
and corrected runs are retained in `artifacts/silo-native-registration/`; no new
macOS, live microsandbox or GUI authentication acceptance is claimed.

### Registration and removal reconciliation (thirteenth patch)

`0013-reconcile-registration-state.patch` extends the same token-bound inspection
API/UI to `pending`, `unconfirmed`, `removal-pending` and `removal-unconfirmed`.
The button is now **Inspect registration**. A matching installed plugin, verified
cache and effective server permit an explicit **Confirm registration** or **Keep
registration** action. Only proven absence of both the plugin entry and VM server
permits **Reset incomplete registration** or **Confirm disconnected**. These actions
change only the owned receipt to registered/removed. They never publish source,
change the Codex profile, install/remove a plugin or restart a process. The normal
Register or Disconnect action remains a separate explicit choice afterward.

Inspection validates the retained bundle and identity, configured marketplace
source when present, relevant CLI entries, cache and transport proof. The token
includes profile/source/receipt/context fingerprints. Missing-marketplace initial
failures are allowed only when the plugin and server are both absent. Disabled,
changed, conflicting or partially present entries are not treated as absence;
independent overrides and changed caches refuse without mutation. The UI distinguishes
absence proof from installed-cache/configuration proof and never implies live SSH
connectivity from either.

Ten native registration tests passed, including five actual CLI tests. The new
seven-scenario test covers failure before marketplace registration, failure after
marketplace add, interrupted pending registration, installed-but-lost registration
reply, failed removal, pending removal and removal with lost verification. It
asserts inspection makes no marketplace-add/plugin-add/plugin-remove request,
stale confirmation refuses, independent MCP overrides/disabled plugins/cache changes
remain preserved, reconciliation keeps bundle/profile bytes intact, and the next
explicit Register or Disconnect succeeds without manual receipt editing. Thirty
frontend tests and TypeScript checking pass, including the four new explicit
confirmation labels. Evidence is `artifacts/silo-native-registration/registration-reconcile.json`.

### Registration panel layout (fifteenth patch)

`0015-registration-panel-layout.patch` makes Register the primary action, keeps
Browse beside each path, and groups Inspect, Review update and Disconnect under
**Manage existing registration**. The selected profile and VM remain visible.
Short state-specific feedback gives the next step; hashes, IDs and connectivity
limitations remain available under details. Confirmation requirements and native
commands are unchanged. Editing a path clears stale confirmation and feedback;
new feedback receives focus, and cancelling a review returns focus to its trigger.

The actual React component and Silo CSS were rendered in Chromium 153.0.8010.12
with only Tauri commands mocked. The original 360px viewport expanded to 636px,
placing actions outside the viewport. The revised component remains within 360px;
all ten checked layouts at 360px and 1280px have no horizontal document or visible
button overflow, including long paths, hashes, expanded details and errors.
Keyboard tests cover tab order, disclosure, explicit confirmation, cancellation
focus, stale path edits and no automatic action on editing. All 30 existing frontend
tests and the full TypeScript check pass. This is browser component evidence, not
a macOS app, native dialog or live VM qualification.

The optional reproducible harness is `app/SiloUI/tests/registration-panel/README.md`
after applying the patch. It uses an existing Chromium/Playwright installation and
a loopback Vite server; it adds no production dependency. Before/after screenshots,
layout measurements and test logs are retained in
`artifacts/silo-native-registration/panel/`.

Patch 0017 refreshes agent guidance for native browser insertion at Unicode grapheme boundaries. Offsets remain code points; unsupported interior boundaries are refused without silently widening a selection.

### Explicit optional browser provisioning (eighteenth patch)

`0018-managed-browser-onboarding.patch` adds **Browser tools** to the running
sandbox's desktop actions. Opening the panel does not provision anything. With a
trusted candidate present, Enable/Disable requires a separate confirmation. An
uncertain attempt cannot be replaced by another choice; **Review setup retry…**
requires explicit confirmation after reviewing the failed guest setup. It reuses
the existing reviewed retry path, never automatically repeats installation or
replays agent actions. Disabling selects a browser-free Luda release; external
Chromium and already running MCP processes are preserved. New conversations use
the selected release.

The shipped `guest/agent-tools-release.json` remains disabled. Maintainers must
select an actual verified Luda source archive as described above; a reviewed
full-commit candidate is now available, but is not selected automatically. That source
must contain managed browser provisioning (`requirements-browser.lock` and
`src/luda/managed_browser.py`). A configured release may additionally carry a
`browser` object with exactly these fields:

```json
{
  "schema_version": 1,
  "executable": "/opt/trusted-chromium/chrome",
  "sha256": "EXPECTED_64_LOWERCASE_HEX_DIGEST",
  "version": "153.0.8010.12",
  "architecture": "aarch64"
}
```

This is a fragment to add to the existing trusted source manifest, not a release
URL or complete manifest. Replace the illustrative digest with independently
verified metadata. The executable/distribution must already exist in the guest;
no browser download, default-on choice, sandbox-policy change or host credential
is added. The digest identifies the executable file, not its complete distribution.
The managed installer validates the actual path, ELF architecture, SHA and bounded
version response as the selected ordinary `silo-desktop` account. The wrapper passes
an owned JSON file to the existing bootstrap's `browser_config` parameter, which
forwards the explicit installer option and account. Older sources lacking this
capability refuse before installation.

Desired selection is recorded separately under the guest's private tools state.
Its normalized digest participates in cached readiness identity alongside source
commit/archive hash. Changing or removing a candidate invalidates old readiness.
Read-only status never installs. The public projection exposes only candidate
availability, requested enablement and the last completed installation choice;
uncertain completion remains null. It does not expose paths, hashes or arbitrary
metadata to the UI, and does not claim a current browser launch or host registration.
A missing candidate explains why enabling is unavailable; a previously requested
candidate can still be disabled after its removal. Candidate changes or an old
unconfirmed attempt require review, not automatic repair.

Guest actions share the existing nonblocking operation lock. Native commands map
only fixed enable/disable/reviewed-retry names, require a running sandbox and use
the existing bounded provisioning timeout (up to65 minutes). A lost reply leaves
status for inspection; it is not proof of success. Desktop startup/viewing remains
independent of the optional browser outcome.

Validation:26 guest-wrapper tests,34 frontend tests and full TypeScript checking
passed. The actual patched Linux Rust module passed17 filtered desktop/registration
tests including five real Codex CLI cases with no skips. The new native test checks
fixed action mapping and strict status projection; guest install callbacks and Tauri
calls are mocked at their stated boundaries. All18 patches applied to a fresh
pinned Silo checkout, and final guest bytes matched the canonical helper. Logs and
patch hashes are retained in `artifacts/silo-managed-browser/`. The separately
qualified managed installer/browser flow does not turn this result into a real
Silo VM, macOS app or browser-artifact provisioning pass.

### Browser completion consistency (nineteenth patch)

`0019-browser-completion-status.patch` requires the same complete-success evidence
for `browser_configured` as for overall readiness. An inconsistent bootstrap result
with `ok: true` but incomplete installation, configuration or readiness now reports
browser completion as unknown. It cannot produce the UI's “Last completed setup
enabled browser tools” claim. This remains historical setup evidence, not a current
browser launch check. The contradictory-result regression and full guest integration
suite pass (27 tests); the patch applies cleanly after0018.

Patch 0020 refreshes the embedded agent skill for explicitly selected cooperating-editor clipboard transport, including clipboard effects and unsupported generic-editor boundaries.

Patch 0021 clarifies the owned-browser field focus prerequisite before selecting text, following the held-out rich-editor agent evaluation.

Patch 0022 documents the explicit owned-browser password-entry exception, including dispatch-only results and clipboard preservation. Other protected-field text tools remain unsupported.

Patch 0023 aligns the bundled skill with inclusive observed list/table ranges, explicit replacement/addition, and the same-inspection endpoint requirement.

Patch 0024 aligns the bundled skill with explicitly declared rich hard breaks, structural boundary readback, and the distinction between paragraph and Shift+Enter policies.

Patch 0025 aligns the skill with direct desktop-tool startup and application-specific formatting guidance derived from the retained first-attempt hard-break evaluation. It adds no formatting operation.

Patch 0026 bounds total decompressed archive bytes before parsing metadata and retains the prior path, payload and entry checks. Nine focused real-archive tests cover PAX/GNU compatibility, expanded metadata, huge declared sizes, concatenated gzip, padding, exact limits, malformed/CRC/truncated streams and recursive metadata chains, and safe disk failure.
