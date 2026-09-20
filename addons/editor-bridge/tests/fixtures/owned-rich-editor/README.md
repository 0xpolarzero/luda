# Production cooperating-editor fixture

Real pinned ProseMirror dependencies match the earlier rich-editor prototype. This fixture imports the production bridge from `/bridge.mjs`; the local HTTP harness serves the exact tracked integration module. No production worker uses `ludaRichProbe`. That older read-only diagnostic remains in the fixture, while the driver's independent oracle is the application's posted actual model/DOM state.

`npm ci && npm run build` rebuilds the committed offline ES-module bundle. The existing lock pins dependencies; `bundle-identity.json` records fixture/bundle/lock and production bridge hashes. `THIRD_PARTY_NOTICES.md` retains runtime dependency licenses. Live runs require no CDN, npm or browser download.

Setup buttons replace/re-register an editor, insert an unsupported image, arm a stored link mark or move focus after the next native input. Those are deliberate synthetic application behaviors, not driver model setters. Native preedit uses real GTK-simple keys. Cancellation uses actual MCP notification only after the independent oracle observes an already-started edit; no remainder is retried.
