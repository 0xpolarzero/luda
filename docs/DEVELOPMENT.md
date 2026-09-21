# Development and releases

## Work on Luda

```sh
uv sync --frozen --extra test
.venv/bin/python scripts/qualify.py
```

Live GUI tests need the system packages listed in [installation](INSTALLATION.md). Run them as an ordinary account (not root) on a private display:

```sh
LUDA_ISOLATED_TEST_DISPLAY=1 xvfb-run -a \
  -s '-screen 0 1440x900x24 -nolisten tcp' dbus-run-session -- \
  .venv/bin/python scripts/headless_tests.py
```

Tests that use an existing shared desktop must hold `/tmp/luda-live-tests.lock` for their entire run. Do not modify applications or files you did not create for the test. Browser and media suites declare their additional dependencies in the [qualification matrix](QUALIFICATION-MATRIX.md).

Tool documentation is generated from the public declarations:

```sh
python3 scripts/build_tools.py
python3 scripts/build_live_coverage.py
```

For the frozen application-outcome skill acceptance suite, fresh agent runners,
and independent live checks, see [skill outcome evaluation](SKILL-OUTCOME-EVALUATION.md).
Agent-behavior acceptance is separate from unit tests and package verification.

## Build downloadable packages

Core Luda and the Editor Bridge are separate Python distributions and separate agent plugins. Core installation must not install the Editor Bridge. The add-on has its own browser dependencies, skill, and application adapter.

Use a clean committed checkout and an isolated build environment:

```sh
python3 -m venv /tmp/luda-build
/tmp/luda-build/bin/python -m pip install --require-hashes -r build-requirements.lock
/tmp/luda-build/bin/python scripts/build_release.py --output dist/release
```

Choose a fresh output directory. The builder uses the committed Git tree, builds wheels and source distributions, verifies runtime and complete skill contents, and creates separate plugin archives. `release.json` records the source commit and package versions; `SHA256SUMS` records asset digests.

A plugin archive contains instructions and an MCP launch configuration, **not the Python runtime**. Its executable must be installed and available to the agent. For a managed prefix or session launcher, generate a configured plugin with `scripts/build_plugin.py` as described in [agent integrations](AGENT-INTEGRATIONS.md).

## Publish a release

1. Run the relevant local tests and require the CI workflows for the candidate commit to pass.
2. Build and inspect the assets from that clean commit. Check that the two installations remain separate.
3. Create a GitHub release for that exact commit, attach the assets and checksums, and describe support limits and installation choices.
4. Use a prerelease label for preview builds. Do not claim packages are on PyPI unless they have actually been published there.

Publishing is a maintainer action. Installing or building Luda does not create tags, publish packages, or modify an agent profile.
