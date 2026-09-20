# Preparing committed source for Silo

`scripts/prepare_release.py` creates an archive, SHA256SUMS, provenance, and a
candidate `agent-tools-release.json` in a fresh directory. It does not publish,
install, modify Silo's disabled manifest, or qualify a release.

Supply the full reviewed commit and the intended immutable HTTPS asset URL:

```sh
python3 scripts/prepare_release.py --commit FULL_40_CHARACTER_COMMIT \
  --source-url https://YOUR_HOST/luda-FULL_40_CHARACTER_COMMIT.tar.gz \
  --output /absolute/fresh-release-directory
```

The helper reads committed Git objects, ignoring local staged, unstaged and
untracked changes. It rejects links, submodules, incomplete source, moving refs,
unsafe URLs and archives exceeding Silo's guest limits. Every archived file's
content and executable bit must match its Git tree entry; export-ignore or
export-subst cannot silently alter the package. Repeated preparation in the
same Git/Python environment produces identical files. Git archive format and
compression implementations may differ across tool versions; provenance records
the Git version, and the generated SHA256 always identifies the actual bytes.

The manifest's URL is intended publication configuration, not proof that an
asset is available there. After publishing those exact bytes, review the URL,
checksum and provenance before installing the manifest into Silo. The helper
does not add an optional browser distribution or provide independent signature
verification. It does not replace release testing or fresh Mac/guest acceptance.

Local validation includes dirty-checkout independence, deterministic output,
attribute-induced omission/substitution refusal, ordinary-file/executable
preservation, immutable commit and URL validation, and extraction with the real
Silo guest helper. Preparing source `9d4f8c0` produced a 1,831,221-byte archive
containing 613 files; the actual guest extractor accepted it. This local candidate
was not published or configured in the Silo product.
