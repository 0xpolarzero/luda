# Pinned Codex CLI qualification dependency

This private npm package is test-only. `@openai/codex` is pinned to 0.155.1, including integrity-locked platform packages in `package-lock.json`. It is not installed globally or added to Luda's runtime installer.

With Node 24 available:

```sh
npm ci --ignore-scripts --no-audit --no-fund --prefix tests/tools/codex-cli
python tests/tools/codex-cli/run_registration_tests.py
```

The runner requires this local executable and exact version before discovering tests. It fails if any focused test skips, and writes CLI version, lock digest and outcomes to `artifacts/codex-cli-registration/result.json`. Actual CLI operations use temporary profiles; no model calls, authentication-file reads or existing profile changes are needed. Host registration/cache checks do not prove SSH transport or Mac/Silo onboarding.

The dedicated Ubuntu 24.04 CI job uses Node 24 and Python 3.12. Local ARM64 validation installed the package with `npm ci` and passed all 15 focused tests without skips using Node 24.21.0 and Codex CLI 0.155.1. Hosted AMD64 execution remains a separate CI result.

Installed `node_modules` is ignored by Git and source fingerprinting; the committed manifest, lock and runner remain fingerprinted. Updating the pin requires regenerating the lock, updating the runner's expected version and rerunning the real CLI contracts.
