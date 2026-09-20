# Public EditorView selection fixture

Test-only variant of the pinned owned-rich fixture. Initial documents exercise emoji, combining characters, paragraphs and strong/em marks. A read-only `ludaSelectionProbe` exposes actual model identity plus public `domAtPos`/`posAtDOM` mappings; it has no model setter. The driver changes only the browser Selection and sends fixed browser-native input or native key events. Actual model, DOM and ordinary textarea values are independently posted to the local oracle.

`npm ci && npm run build` regenerates the offline ES-module bundle. The lock and licenses match the qualified pinned ProseMirror dependencies; `bundle-identity.json` records bundle/source/lock hashes. Live runs need no CDN or npm access. Setup controls intentionally exercise same-length application updates, view registration and focus races; these are not hidden driver mutations.
