# Real guest-wrapper composition

The local Linux composition passed on 2026-09-20. This is a real download, extraction, installation and desktop-readiness test, not a mocked installer. It does not qualify a fresh Mac/microsandbox, host Codex registration, the Silo Rust/React hooks, or apt provisioning.

The reusable test is `tests/live_silo_composition.py --revision FULL_COMMIT --output /workspace/FRESH_DIRECTORY`. Run as guest root with the desktop account already provisioned. It holds `/tmp/luda-live-tests.lock` around bootstrap, readiness and installed-payload checks. It creates only its fresh output tree, retaining the isolated installation and logs for inspection; it does not select or modify another installation. The HTTPS server binds only `127.0.0.1`, shuts down in `finally`, and uses a fresh one-day certificate. A request without that trust must fail certificate verification; the wrapper then trusts exactly this certificate via `SSL_CERT_FILE`. No TLS verification is disabled.

Recorded run: `/workspace/luda-silo-composition-run-1/result.json`, with trusted installer output in the adjacent `installer.log`. Pinned source commit `c87e0a3059b4da8444f8fedd07383cd517c85182` was archived using `git archive`, with archive SHA-256 `2b75b9f9f65b7d577224d470d6a4ae217d21fabe7ea8b48139953bb28e7aeed4`. The wrapper was semantic integration commit `6baf9f3` (including restrictive extraction modes and durable preflight errors), helper SHA-256 `6931b1456e700804c79030403e995993ce6fde1620f17ff5cd17c4bd6fd14f14`.

The actual wrapper downloaded and verified the archive, extracted its source and invoked the extracted `bootstrap_guest.bootstrap`. The only installer substitution was a test callback supplying the ordinary four positional arguments plus `skip_system=True`, avoiding concurrent apt operations. Production `agent-tools.bootstrap` does not supply that flag: this run proves the composed bootstrap/download/extraction path on an already provisioned guest, not that exact production callback or package provisioning.

Observed results:

- Installation selected `0.1.0-98cde358c2a512e5`; configuration generation and doctor readiness succeeded for `silo-desktop` UID 1001.
- Persisted status and subsequent status reads reported ready. A repeated `ensure` did not call the installer again; selected manifest bytes and modification time were unchanged.
- An independent process as UID 1001 read the installed release manifest and skill. Private root-owned attempt/config bundles remain private; host transfer is still an explicit separate operation.
- Installed payload hashes were independently verified against the manifest immediately after the initial run. The reusable script now performs that same check inside its leased run. Manifest SHA-256: `8666f41796d1effd4988e747f64a84cdd43b99d17589c37f533f94d2e9bb11bd`.
- The HTTPS server stopped. The synthetic test creates no application documents or typed credentials and does not alter the desktop lifecycle.

No first-attempt failure was normalized away: the initial composition succeeded. Its raw result records the post-run integrity check distinctly. The package manager and Python dependencies were already present, and the shared desktop was already running; failure recovery, provisioning from an empty image and host discovery require their own evidence.
