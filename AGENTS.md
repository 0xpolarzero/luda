# Luda development

The user requests exhaustive features, simple intuitive agent tools, comprehensive tests, parallel work and atomic conventional commits. Do not equate dispatched input with verified application state or mark catalog cases qualified without evidence.

- Work in a dedicated git worktree/branch for each parallel task. Commit atomic changes with conventional messages. The primary agent integrates and pushes main; agents do not force-push or change main.
- Keep runtime source, documentation, skill and schemas aligned. Preserve actual desktop account `silo-desktop`; Luda is the product/package name.
- Use local unit tests for contracts and independent application/file/DOM oracles for live effects. Include failure and timeout cases. Production qualification is distinct from a small local probe.
- Tests on the shared `:1` desktop MUST hold `/tmp/luda-live-tests.lock` for their entire lifetime. Example: `flock /tmp/luda-live-tests.lock /absolute/worktree/.venv/bin/luda-session -- /absolute/worktree/.venv/bin/python /absolute/worktree/tests/live_backend.py`. Other agents may run unit tests concurrently. Do not kill or modify desktop apps you did not launch.
- Runtime uv is available at `/workspace/silo-desktop-evaluation/bin/uv`; Chromium for offline tests is `/workspace/silo-desktop-research/browsers/chromium-1243/chrome-linux-arm64/chrome`. Each worktree should create its own venv so imports do not accidentally test another branch.
- No vendor/model API credentials or public network listener should be needed for local desktop use. No user text/screenshots in logs by default. Use argv/stdin rather than shell interpolation.
- Update evidence and blockers honestly. Never turn an untested feature into a claim of complete support. Preserve user-created files and repository history.
