# Luda

An experimental local Linux desktop MCP server and agent skill, with an explicit feature/acceptance catalog. Runs on the existing microsandbox XFCE/X11/KasmVNC desktop. No AIO/Cua worker, cloud service, model API or nested VM.

**Status: working prototype, not production-qualified.** A tool can return `dispatched` without the application doing what you intended. Exact text replacement and window activation have specific readback checks. Clipboard insertion does not claim destination verification.

## Deliverables

- [345 acceptance cases in 34 feature areas](docs/REQUIREMENTS.md), with [machine-readable catalog](docs/requirements.json).
- [Architecture and behavioral contracts](docs/DESIGN.md).
- [Implemented coverage, test evidence and release blockers](docs/VALIDATION.md).
- [Agent skill](skills/luda/SKILL.md).
- `src/luda`: 14 typed MCP tools, session launcher, X11 geometry, isolated AT-SPI worker, clipboard input and screenshots.
- `tests`: native fixture, real application checks and actual stdio MCP integration.

## Tools

| Tool | Contract |
|---|---|
| `desktop_doctor` | Actual session/display/dependency/accessibility checks |
| `desktop_windows` | Window identities, focus, client/frame geometry |
| `desktop_activate` | Activate and verify exact window identity |
| `desktop_observe` | Screenshot, image/native geometry and expiring snapshot ID |
| `desktop_inspect` | Bounded, window-scoped accessibility tree and expiring element IDs |
| `desktop_read_text` | Exact accessible text with explicit truncation |
| `desktop_set_text` | Full editable-text replacement with exact readback |
| `desktop_enter_text` | Explicit clipboard shortcut; destination remains unverified |
| `desktop_press_keys` | One intentional chord; not a text-typing substitute |
| `desktop_click` | Recent screenshot coordinates in active client bounds |
| `desktop_scroll` | Discrete wheel ticks at a validated point |
| `desktop_drag` | Same-window drag, with button-release cleanup attempt |
| `desktop_focus_element` | Request focus on an enabled/showing element |
| `desktop_invoke` | Advertised semantic action, not an assertion of app outcome |

## Install in a guest

For Ubuntu 24.04 with an existing XFCE/X11 desktop:

```bash
sudo bash scripts/install.sh /opt/luda-0.1.0
```

The script provisions explicit apt dependencies and installs hash-pinned Python runtime requirements. The Python project itself is built from this checkout. It does not replace the desktop, edit Codex configuration, or start a public network listener. Use a new versioned directory for upgrades; automated upgrade/rollback is not implemented.

For development with uv:

```bash
uv sync --frozen --extra test
.venv/bin/luda-session --user silo-desktop -- .venv/bin/luda
```

Run the launcher as root or the desktop account. It reads that account's XFCE environment and runs the server as that account. If multiple XFCE sessions exist, pass `--session-pid`. Paths supplied to the server should be absolute in an actual Codex configuration.

## Codex remote-context configuration

The following is a configuration example for the **guest execution context**, using the install path above. This example has not been tested through the Mac app's fresh SSH onboarding flow. Verify which Codex configuration the selected remote context loads; configuring the Mac host to run a guest-only path is not sufficient.

```toml
[mcp_servers.luda]
command = "/opt/luda-0.1.0/.venv/bin/luda-session"
args = ["--user", "silo-desktop", "--", "/opt/luda-0.1.0/.venv/bin/luda"]
startup_timeout_sec = 20
tool_timeout_sec = 20
```

Copy the included `skills/luda` folder into the skill directory of the Codex account executing in that guest, for example `~/.codex/skills/luda`. Do not overwrite an existing skill of that name without inspecting it. A new task should then discover the skill and MCP tools. The current project deliberately does not modify an existing Codex account's global configuration.

## Test

Tests create only owned fixtures/documents and terminate their own applications. Run them against a disposable agent desktop: they necessarily change focus and clipboard contents. Native tests require GTK3 Python typelibs and Mousepad; application tests also require XFCE Terminal and a Playwright-compatible Chromium.

```bash
python scripts/build_requirements.py
.venv/bin/python -m unittest discover -s tests -p 'test_*.py'
.venv/bin/luda-session -- .venv/bin/python tests/live_backend.py
.venv/bin/luda-session -- .venv/bin/python tests/live_mcp.py
.venv/bin/luda-session -- .venv/bin/python tests/live_apps.py --browser /absolute/path/to/chromium
```

Use absolute paths if launching from a different directory. `artifacts/` is gitignored and stores local synthetic test evidence. The browser helper uses Playwright only for offline setup and independent readback; desktop input comes from this driver.

## Known limits

The acceptance catalog is intentionally broader than this implementation. Missing capabilities include generalized state waits, window move/resize management, cross-window drag, verified universal insertion, human takeover, cancellation guarantees, automatic reconnection after X-server restart, richer clipboard types, Wayland and browser DOM control. Qt/Electron/Firefox and AMD64 are not qualified. X11 focus races and unmanaged overlay interception remain possible. The worker's accessibility mapping can refuse apps whose reported top-level bounds do not match X11 geometry.

Clipboard contents are overwritten, PRIMARY remains separate, and a terminal can execute pasted newlines. Protected fields are unsupported for semantic read/write. No private user documents are included in tests or logs. See the design and validation documents before treating this as a release component.
