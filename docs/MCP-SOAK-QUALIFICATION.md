# Sustained public MCP session qualification

`tests/live_mcp_soak.py` adds a ten-minute sustained-use probe for **PERF-09**, with observations relevant to **PERF-03/PERF-05/PERF-06/DIAG-09/MCP-08**. It complements the existing 28-iteration direct-Desktop resource test. It does not establish hours-long endurance, a hard RSS ceiling or universal application performance.

The test uses a single persistent public stdio MCP connection in a private 1200×900 Xvfb/D-Bus/XFWM session under ordinary UID 1001. All XDG paths are private before the bus starts. A GTK fixture owns the only application UI. Each cycle freshly inspects the tree, replaces synthetic Unicode/multiline/tab text, reads it back, explicitly invokes a button and captures a 640-pixel-wide screenshot. Every tenth cycle also focuses the field, sends Ctrl+A and replaces it through the clipboard. The fixture writes its own text and action count independently; both must match after every cycle.

After the workload stops, independent reads must remain unchanged for three seconds before MCP disconnect and two seconds afterward. The server must exit on normal transport cleanup, its owned clipboard process must disappear, and tagged process cleanup must report no survivors. These are measured quiet intervals, not proof against arbitrarily delayed external side effects.

## Resource and timing interpretation

Samples are taken between completed requests, after a 50 ms drain interval. They record server/client file descriptors, RSS and thread count, server descendants and the complete private-session process count. One intentional `xclip` owner may remain; completed accessibility, screenshot and input helpers may not accumulate. This does not sample short-lived helper resource peaks.

The test has broad regression alarms of 64 server descriptors and 512 MiB RSS. These catch gross regressions, not ordinary allocator/cache growth, and are not product limits. Reported steady-phase statistics omit the first five cycles; raw samples retain warm-up. Request latencies measure the actual client tool round trip separately from independent application readback.

Only the first and last screenshots are saved. Request logs contain tool names, timing and outcome labels, not input text or screenshot payloads. The synthetic fixture and full source fingerprints are recorded; the run fails if source files change during it.

## Reproduce

Run in a writable checkout as the ordinary desktop account:

```sh
.venv/bin/python tests/live_mcp_soak.py --seconds 600
```

For a root-owned development checkout:

```sh
mkdir -p artifacts/mcp-soak
chown desktop:desktop artifacts/mcp-soak
runuser -u desktop -- .venv/bin/python tests/live_mcp_soak.py --seconds 600
```

The runner creates a private session itself. It never uses the shared desktop. Results go to a unique `artifacts/mcp-soak/run-*/` directory; `--output` selects an explicit fresh location. `--seconds 12` is useful for harness smoke tests but must not be reported as sustained-use evidence. The outer watchdog allows workload duration plus 60 seconds for startup/shutdown. The ordinary matrix runner's 300-second maximum is intentionally not used for this ten-minute run.

## Recorded run

The first full run passed on Linux 6.12.99 aarch64 / glibc 2.39, UID 1001, from commit `ff54c47`. Its actual workload lasted **600.270 seconds**, completing **399 cycles and 2,120 MCP requests**, including 40 clipboard replacements. The independent final button count was 399. There were no tool errors or application-state mismatches.

After five warm-up cycles, 394 resource samples reported:

- Server descriptors: exactly **7** throughout. Server thread count: **4**.
- Server RSS: **64,552–64,900 KiB** (about **63.0–63.4 MiB**); median **64,884 KiB**. This measured variation is not treated as leakage or a universal ceiling.
- Client RSS: **60,136–60,144 KiB**. Client descriptors stayed at **11**.
- Private-session process count: **12–13**. Exactly one current `xclip` process remained below the server between requests; no completed helper descendants accumulated.

Measured public tool round-trip latency (milliseconds):

| Tool | Calls | Median | p95 | Maximum |
| --- | ---: | ---: | ---: | ---: |
| `desktop_observe` | 400 | 281.0 | 303.6 | 414.9 |
| `desktop_inspect` | 399 | 97.3 | 129.7 | 140.9 |
| `desktop_type` | 399 | 93.6 | 103.8 | 117.0 |
| `desktop_read_text` | 399 | 69.3 | 77.9 | 122.9 |
| `desktop_invoke` | 399 | 87.7 | 94.4 | 146.8 |
| `desktop_press_keys` | 40 | 150.2 | 160.0 | 160.3 |
| `desktop_paste` | 40 | 209.2 | 222.4 | 226.4 |

The independent fixture remained unchanged for the three-second pre-disconnect and two-second post-disconnect checks. Normal MCP transport shutdown removed the server and clipboard owner. Outer cleanup found **zero remaining tagged processes**. No runtime changes were needed.

Raw evidence is in `artifacts/mcp-soak/ten-minute-1/`: `results.json`, `samples.jsonl`, `requests.jsonl`, two screenshots, logs and `cleanup.json`. Total artifacts remain below 1 MiB. The earlier `smoke-1/` run passed for 12.034 seconds / eight cycles; it is retained separately and is not counted as ten-minute evidence.

Before/after source fingerprints matched exactly: `6d5db61016e78b2cbe8105b0478766862df2d30260e8ed7bb1b691dfbfd3cbe7`. The evidence records the source before this report was added.

Limitations: one small GTK tree, one window, one serial client and moderate request cadence. This does not measure concurrent-client saturation, large images/trees, low-memory pressure, CPU utilization, full-session peak memory, disconnect during an outstanding mutation, or arbitrary delayed effects. Existing dedicated fault and cache-bound tests remain necessary.
