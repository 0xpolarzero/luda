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

The Linux helper reads committed Git objects with replacement objects disabled,
ignoring local staged, unstaged and untracked changes. It rejects links,
submodules, incomplete source, moving refs,
unsafe URLs and archives exceeding Silo's guest limits. Every archived file's
content and executable bit must match its Git tree entry; export-ignore or
export-subst cannot silently alter the package. Repeated preparation in the
same Git/Python environment produces identical files. Git archive format and
compression implementations may differ across tool versions; provenance records
the Git version, and the generated SHA256 always identifies the actual bytes.
Publication uses Linux `renameat2(RENAME_NOREPLACE)`, preserving even an empty
destination directory created concurrently. Unsupported publication fails
without replacing the destination.

The manifest's URL is intended publication configuration, not proof that an
asset is available there. After publishing those exact bytes, review the URL,
checksum and provenance before installing the manifest into Silo. The helper
does not add an optional browser distribution or provide independent signature
verification. It does not replace release testing or fresh Mac/guest acceptance.

Local validation includes dirty-checkout independence, deterministic output,
attribute-induced omission/substitution refusal, ordinary-file/executable
preservation, immutable commit and URL validation, and extraction with the real
Silo guest helper. Independent review reproduced two initial gaps: replacement
refs could change the archive while retaining the requested commit label, and
ordinary rename could replace a concurrent empty directory. Both are corrected
with actual Git/filesystem regressions. Preparing source `9d4f8c0` produced a 1,831,221-byte archive
containing 613 files; the actual guest extractor accepted it. This local candidate
was not published or configured in the Silo product.

## Available canonical GitHub source

The [reviewed candidate](../integrations/silo/releases/20af806.json) points to the
already available full-commit GitHub archive for `20af806b0a68b49f431a9ada97d01e09e0af2b2e`.
Its actual HTTPS download, checksum, complete Git-tree comparison and guest
extraction passed; [retained evidence and rerunnable verifier](../tests/evidence/source-archive/README.md)
record the exact scope. The guest default manifest remains disabled. Selecting
this candidate requires no separate release upload, but still requires explicit
integration selection and product acceptance.

These are GitHub's archive bytes, not `prepare_release.py` output. For this same
commit the canonical download is 3,545,071 bytes with SHA-256
`13e16f90217c480c84427faadd9eb39f4bc40ebcd1133624cb071bc87a942850`;
the separately prepared local archive is 3,540,387 bytes with SHA-256
`27cee8f7c9652d9143bcb433d50078b9d74598e5c43eda9ed22166927310993a`.
Both contain the same 672 Git files. Never pair the local builder's checksum with
the canonical URL. The builder intentionally requires its own generated filename,
so that URL is not an accepted `--source-url` for local preparation.

GitHub may change archive encoding/compression while retaining the commit's tree.
A pinned checksum then fails closed and requires another review; no automatic
checksum update is permitted. This proves correspondence to the user-reviewed
repository commit, not an independent publisher signature, offline installation,
a release qualification or a real Mac/Silo deployment.
