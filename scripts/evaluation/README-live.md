# Fresh live confirmation runner

Run `skill_live.py` only after the same frozen skill and fixtures have passed two complete 23-case benchmark batches. Each invocation starts one fresh ordinary-account XFCE session with its own Xvfb display, DBus session, HOME and Codex session. It never attaches to `:1` and does not require desktop account names in the product.

Supply real Greybird assets in a directory containing `themes/Greybird/gtk-3.0/gtk.css` and `themes/Greybird-dark/gtk-3.0/gtk.css`. The recorded capture used the official Ubuntu `greybird-gtk-theme_3.23.3-1_all.deb` extracted into `/tmp/luda-greybird`; its URL/hash are retained in the screenshot fixture provenance. The runner copies assets into each private HOME and never installs a system theme. The repository's `.venv` must contain this checkout's Luda installation. Invoke from the repository root as the coordinator account that can run the explicitly chosen ordinary GUI account:

```sh
.venv/bin/python scripts/evaluation/skill_live.py --prepare-only --user ubuntu --themes /tmp/luda-greybird/usr/share
```

`--prepare-only` starts no evaluated agent. It checks exact accepted skill bytes and baseline reference hashes, resets the private session to Greybird, verifies the initial theme and selected row independently, captures initial/final screenshots, and exercises owned-process cleanup. For a real confirmation after the repeated benchmark gates, omit that flag:

```sh
.venv/bin/python scripts/evaluation/skill_live.py --user ubuntu --themes /tmp/luda-greybird/usr/share
```

After independently accepting the first live result, invoke the same command again for a second fresh confirmation. A failed live check rejects the candidate; retain the failure rather than retrying until a passing result appears. Neither command labels a run an acceptance pass automatically.

The agent receives the exact public appearance task from `skill_interactions.py`, the installed accepted skill and all seven original references. It receives no target sequence, expected result oracle, screenshot corpus, or evaluator criteria. The shared isolated interaction runner uses `gpt-5.6-sol`, no reasoning-effort override, and Codex CLI 0.155.1. Authentication is linked temporarily using that runner and never retained in artifacts. Shell execution is disabled; all recorded agent tool events must be public Luda GUI calls. The exact task, installed file hashes, session identity, final answer, full events, errors and GUI-only audit are retained beneath each run's `agent/` directory.

The desktop evaluator independently reads `/Net/ThemeName` through `xfconf-query`, obtains selected states with a separate system-Python AT-SPI traversal, captures actual desktop screenshots, and records the live Appearance process/window before and after the agent. These evaluator-only accesses are never sent as tools to the agent. Inspect `initial.json`, `initial.png`, `final.json`, `final.png`, `agent/events.jsonl`, `agent/final.txt`, and cleanup evidence. A valid live confirmation additionally needs manual assessment of dark unselected application content and ordinary controls, correct selected/applied theme, a visible Appearance page, a subsequent agent observation, and an accurate final claim. A dark background, highlighted label, or accepted activation receipt alone cannot pass.

Desktop logs and failed setup results are preserved. `recorded_awaiting_review` means only that evidence was captured; a timeout, unsupported trace, tool error or wrong final claim must be assessed honestly, and an unassessable run cannot pass. Fixture captures and setup preflights are not live evaluated-agent results.
