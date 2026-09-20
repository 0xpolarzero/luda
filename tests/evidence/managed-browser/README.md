# Installed managed-browser qualification

First install this checkout with an explicit browser configuration into a disposable
owned prefix as documented in `docs/MANAGED-BROWSER.md`. Then run as an ordinary
account with a writable output directory and an existing checkout `.venv`:

```
python3 tests/evidence/managed-browser/run.py --repo /absolute/checkout \
  --prefix /absolute/managed-install --output /absolute/fresh-evidence
```

Requires Xvfb/xvfb-run, xauth, D-Bus, XFCE and the separately provisioned verified
Chromium153.0.8010.12 (this fixture's explicit expected version). The runner creates
private HOME/XDG directories before D-Bus and starts an owned real xfce4-session.
MCP is the actual installed wheel, launched using its `luda-session` with the
explicit session PID. An intentionally wrong ambient executable must be ignored.
Doctor's version evidence, actual browser launch, Unicode/newline editing against
a loopback HTTP oracle and profile/process cleanup after EOF must pass. No shared
desktop, existing browser profile or external network page is used. This is Linux
managed-launcher evidence, not Silo UI, macOS or arbitrary browser compatibility.

Recorded local qualification: Linux ARM64 UID1001, installed release
`0.1.0-77e7d8e0eda34f53`, Chromium153.0.8010.12, Playwright1.63.0. Final runtime
modules matched the installed wheel byte-for-byte. Browser-free installation had
no Playwright; repeat installation and base/browser rollback passed. Detailed
wheel/source hashes, live result and lifecycle result are retained in
`/workspace/luda-managed-browser-artifacts/qualification.json` in this development
environment. The first version-label parsing failure and two fixture plumbing
failures (wire method argument collision and small readline limit) are retained
alongside corrected runs; none is counted as a product pass. Sixty-eight focused
installer, bootstrap, session and browser checks passed. Hosted and Silo onboarding
qualification remain separate.
