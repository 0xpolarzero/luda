# Standalone Linux qualification

Source `830a3c41838e4adb7b5ea65171d7b3f459d20ed7`, unchanged fingerprint `df314fec662229ae051a0dc6217dd691faf23529632011a8ec803b952f17ab0d`:

- Root: 920 tests, 919 passed, one unavailable build-tool skip, 35.427 seconds.
- Ordinary account: 920 tests, 917 passed, three skips (build tools, unavailable Codex CLI, root-only access probe), 35.378 seconds.
- All 17 private native X11 suites passed, including real MCP, Unicode/multiline paste, cancellation, control, menus, geometry, resource pressure and input cleanup.
- Private semantic suite passed in 6.368 seconds; workspace snapshot suite in 2.474 seconds.
- Actual locked installation under umask077 produced `0.1.0-65a2d1d35ffdb8c7`. An ordinary account independently matched all 50 installed runtime modules and the skill to source.
- Installed-interpreter private native and MCP suites passed in 8.348 and 3.093 seconds. The server executable came from that installed release.
- Three build-source regressions, including actual wheel construction, passed separately with locked build tools.

Original failures are retained: the initial cleanup run found three stale test expectations and premature invoking-account lookup despite an explicit account. The launcher lookup was fixed; fixtures now test the renamed private runtime directory and generic instructions. The initial install probe stopped before installation because its evidence parent did not exist; creating the test parent resolved this harness invocation error. Neither failure is relabeled as a pass.

Records describe their exact source and environment, not every Linux desktop. No application-manager integration or host-platform acceptance is required. Hosted CI is recorded separately in current validation documentation.
