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
remain HTTPS and satisfy the same rule. Download limits are 32 MiB and 120 seconds
plus a bounded final socket read; extraction limits are 128 MiB and 10,000 members.
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

Apply patches in lexical order to a clean checkout of the pinned Silo commit:

```sh
git -C /path/to/silo rev-parse HEAD
git -C /path/to/silo apply --check /path/to/luda/integrations/silo/0001-guest-onboarding.patch
git -C /path/to/silo apply /path/to/luda/integrations/silo/0001-guest-onboarding.patch
```

Canonical guest assets are also retained alongside the patch for review. Luda's
`tests/test_silo_integration.py` checks manifest validation, checksum/HTTPS policy,
archive restrictions, pending/start sequencing, durable interruption state,
no automatic retries/upgrades, sanitization and byte-identical patch application.
Run `python3 -m unittest discover -s tests -p test_silo_integration.py` from Luda.
Qualification fingerprints include `integrations/`.

These tests do not exercise a fresh microsandbox, packaged Mac app, actual source
server or host Codex placement. Those remain separate acceptance work. Configure
the artifact, verify the generated bundle in the intended remote executor/profile,
and exercise doctor plus an owned-file GUI task before claiming onboarding works.
