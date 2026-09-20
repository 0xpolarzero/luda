# Canonical source archive proof

On 2026-09-20 the full-commit GitHub source in [the candidate manifest](../../../integrations/silo/releases/20af806.json) downloaded over HTTPS and redirected to HTTPS codeload. Its 3,545,071 compressed bytes fit the guest's 32 MiB bound. All 672 file contents and executable bits plus 53 directory entries match `git --no-replace-objects` at the exact commit. Raw GitHub modes are 0664/0775; the actual trusted local guest extractor accepts the declared root and normalizes files to 0644/0755, directories to0755 inside a private0700 destination. Expanded file bytes are7,176,903, within128MiB;725 entries fit the10,000 cap.

The actual guest downloader fetched the same pinned bytes again. The packaged verifier then repeated download, full-tree comparison and extraction successfully. No downloaded code was executed, and no managed/Silo manifest was enabled. Only the reviewed local Git helper is imported by the verifier. No network headers, cookies, credentials or full source archive are retained here.

Run against a trusted local checkout containing the full commit, with a new disposable output directory:

```sh
python3 tests/evidence/source-archive/verify.py \
  --repo /absolute/trusted/luda \
  --manifest integrations/silo/releases/20af806.json \
  --output /absolute/new-private-proof-directory
```

This test downloads and extracts source but never invokes its installer. The candidate's `enabled:true` describes a selectable configuration; it is not the default guest manifest, which remains disabled. GitHub archive packaging may change, causing the pinned checksum to refuse. A separately generated local archive has different bytes/checksum despite matching the same tree; see result.json. These proofs remove URL absence as a delivery blocker, not the remaining real Silo/Mac integration and fresh-task acceptance requirements.
