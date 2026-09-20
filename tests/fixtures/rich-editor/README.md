# Offline rich editor fixture

This test-only fixture uses the real pinned ProseMirror basic schema, `baseKeymap`,
and explicit Ctrl+B/Ctrl+I mark commands. It is a minimal cooperating editor,
not the complete ProseMirror example setup. In particular it does not bind
Shift+Enter to the schema's `hard_break` node.

`editor.bundle.js` is committed so live tests need no CDN or npm access.
`package-lock.json` pins transitive packages; `bundle-identity.json` records
runtime versions and source/bundle/lock SHA-256. Rebuild with Node and npm:

```sh
npm ci
npm run build
```

Update the recorded hashes after reviewing any deliberate source/dependency
change. Keep generated `node_modules` outside the qualification source tree:
source fingerprints include fixture files. Bundled runtime MIT licenses are
in `THIRD_PARTY_NOTICES.md`; esbuild is a build-only dependency.

The cooperating read-only API reports actual DOM and ProseMirror state. The
application independently posts snapshots to the test's loopback oracle after
transactions. Neither interface accepts inserted text or model mutations from
the driver. Deliberate fixture buttons model document replacement, image nodes,
and a **synthetic** pending composition event; the latter is not an IME test.

The declared model text representation separates paragraphs with one LF and
maps a `hard_break` to one LF. The model JSON remains available to distinguish
those structurally different meanings. Empty-editor DOM filler and rendered
`innerText` are recorded separately, never silently normalized into model text.
