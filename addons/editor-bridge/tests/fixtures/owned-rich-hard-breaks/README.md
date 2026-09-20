# Cooperating hard-break qualification fixture

This test-only app uses the same pinned ProseMirror dependency lock and licenses
as owned-rich-editor. It adds an actual Shift+Enter command creating hard_break
nodes and opts into the production bridge. Visible setup buttons deliberately
create mixed marked documents, legacy declarations and an incorrect binding.
The driver never calls model setters; the app independently posts its real model,
native selection, rendered DOM and trusted input events.

Rebuild with npm ci and npm run build using the checked-in lock. The offline
bundle has no runtime CDN requirement. Node 24.11.0 built this fixture;
bundle-identity.json records source/bundle/lock and external bridge hashes.
