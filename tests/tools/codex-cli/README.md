# Pinned Codex CLI qualification dependency

This private npm package is test-only. `@openai/codex` is pinned to 0.155.1, including integrity-locked platform packages in `package-lock.json`. It is not installed globally or added to Luda's runtime installer.

With Node 24 available:

```sh
npm ci --ignore-scripts --no-audit --no-fund --prefix tests/tools/codex-cli
python tests/tools/codex-cli/run_registration_tests.py
```

The runner requires this local executable and exact version before discovering tests. It fails if any focused test skips, and writes CLI version, lock digest and outcomes to `artifacts/codex-cli-registration/result.json`. Actual CLI operations use temporary profiles; no model calls, authentication-file reads or existing profile changes are needed. Registration checks establish discovery in the tested client profile; graphical access is tested separately.

The dedicated Ubuntu 24.04 CI job uses Node 24 and Python 3.12. The standalone runner executes the six plugin-bundle contracts, including actual registration in a temporary profile. It also tests the new setup flow: generated MCP configuration is read by `codex mcp get`, and the app server discovers the installed user skill through `skills/list`. The app-server requests have bounded timeouts, run with isolated HOME and CODEX_HOME, and never start a model turn or desktop server. Removed machine-integration contracts are not part of this suite.

Installed `node_modules` is ignored by Git and source fingerprinting; the committed manifest, lock and runner remain fingerprinted. Updating the pin requires regenerating the lock, updating the runner's expected version and rerunning the real CLI contracts.
