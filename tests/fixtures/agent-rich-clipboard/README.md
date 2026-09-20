# Fresh-agent rich edit fixture

Test-only local application. Initial content is a bold prefix, a plain unique middle string containing a combining sequence, and an italic suffix. Edits use public Luda tools. The visible save button reads the actual ProseMirror model and rendered DOM into a private independent oracle; it does not read requested driver values.

The bundle uses the exact package versions and lockfile copied from the qualified `pm-selection` fixture; see `bundle-identity.json` and `THIRD_PARTY_NOTICES.md`. Build `app.js` with esbuild0.25.5, bundle/ESM/minify, preserving `/bridge.mjs` as external. The local test server serves the current shipped cooperating bridge. No external web resources are loaded.
