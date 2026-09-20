# Basic international font rendering

Exact text storage does not guarantee readable screenshots. A fresh-agent draft test saved Japanese correctly, but the final GTK screenshot displayed missing-glyph boxes. The independent Pango oracle reproduced missing glyphs before provisioning fonts.

`scripts/install.sh` now adds the Ubuntu packages `fonts-noto-core`, `fonts-noto-cjk`, and `fonts-noto-color-emoji`. This supplies fallback fonts without editing user/application font settings, replacing user fonts, or changing locales. The tested packages add roughly 141 MiB before distro-recommended extras. Apt updates the fontconfig cache; existing applications with cached font maps may need to be reopened. An installation using `--skip-system` must provide equivalent fonts separately.

The tested arm64 Ubuntu packages were:

- `fonts-noto-core` 20201225-2
- `fonts-noto-cjk` 1:20230817+repack1-3
- `fonts-noto-color-emoji` 2.047-0ubuntu0.24.04.1

Pango 1.52.1 and Cairo 1.18.0, running as desktop uid 1001 with ordinary `Sans` and automatic system fallback, produced these missing-glyph counts:

| Sample | Before | After |
| --- | ---: | ---: |
| Japanese | 6 | 0 |
| Simplified Chinese | 6 | 0 |
| Traditional Chinese | 6 | 0 |
| Korean | 4 | 0 |
| Emoji family/skin-tone/ZWJ sequences | 7 | 0 |
| Combining accents | 0 | 0 |
| Arabic | 0 | 0 |
| Devanagari | 12 | 0 |

The generated after-image was also inspected: CJK characters are readable, the emoji samples render as joined pictographs, and combining accents are visible. Additional Thai, Tamil, Bengali, Hebrew and Ethiopic samples report zero missing glyphs. This is sample glyph coverage, not proof of correct typography, bidirectional editing, grapheme editing, all glyph variants or every character in those scripts.

Coverage remains incomplete. Probed codepoints U+105C0, U+1E4D0 and U+31350 still each report one missing glyph with these distro versions. The latter two include a Nag Mundari letter and a supplementary CJK ideograph. Applications needing newer Unicode scripts, specialized symbols or private-use fonts need additional appropriate fonts. Those explicit additional probes are recorded separately and do not count as passing basic coverage.

Reproduce without opening a desktop or changing font settings:

```sh
/usr/bin/python3 tests/live_font_rendering.py --output /absolute/new/evidence-directory
```

The test needs the optional distro Python GI/PangoCairo/Cairo bindings. It refuses an existing evidence directory, writes `results.json` and `rendered.png`, and exits nonzero if any required sample has missing glyphs. Font package versions and additional unsupported-codepoint probes are included. Before, after and expanded evidence remain in `artifacts/fonts/before`, `artifacts/fonts/after` and `artifacts/fonts/after-expanded` in the qualification worktree. The failed baseline is retained rather than replaced with the successful result.

## Doctor diagnostic

`desktop_doctor` and `luda doctor` include `font_coverage`: `covered`, `partial`, or `unavailable`. The diagnostic checks the same eight fixed samples above using the selected desktop account's default Sans fallback. A partial result names missing samples and includes their unknown-glyph counts; it does not imply text corruption. Covered means those samples have glyphs, not universal Unicode support or correct application-specific rendering.

The helper runs in isolated system Python with a three-second deadline and an 8 KiB output limit. It uses Pango's font map and glyph-coverage count without creating a rendering surface, screenshot, artifact or log, and accepts no user text. Provider failure, missing dependencies, resource exhaustion or malformed output produce an explicit unavailable result. Cancellation propagates. `gir1.2-pango-1.0` is an explicit system dependency.

Font coverage never participates in desktop readiness or input admission. An unavailable font provider or a missing sample leaves other supported controls available; it does not bypass session lock, pause, focus or application-capability checks. Unit tests verify readiness and capability classification remain unchanged for partial/unavailable results. The real `tests/live_font_diagnostic.py` probe verifies covered Noto defaults and partial coverage under a temporary DejaVu-only font configuration, without altering the caller's environment or user font settings.
