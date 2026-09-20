# AT-SPI provider identity

A process ID does not identify one AT-SPI application connection. Object paths are
local to a D-Bus provider, and two providers in the same process can reuse them.
The previous worker selected a top-level by geometry, kept only its path, then
traversed every matching path in that process. A deterministic two-provider
fixture exposed both trees; a later mutation could choose the first colliding
path even when it belonged to the other provider.

Scoped handles now retain the provider's unique D-Bus connection name alongside
the top-level path. Scoped traversal admits only that connection, and refuses
cross-provider descendants as incomplete coverage. A disappeared provider does
not rebind to another provider with the same process, path, role and name. The
provider field stays in the server's private handle cache, not public inspection.
Missing identity or a well-known alias does not authorize a broader search.

`tests/test_provider_identity.py` covers geometry-selected inspection, colliding
mutation targets, provider disappearance, missing identity, foreign descendants
and alias refusal. The public-inspection test also checks that the private field
is retained internally and omitted from responses. The isolated real GTK semantic
suite passed using the distro GI `Accessible.app.bus_name` field (`:1.2` in this
run). These tests establish the collision bug and fix without claiming a live
Chromium collision: the investigated Chromium chooser inspection correctly
reported unavailable; its misleading earlier tree artifact was stale.

This is connection scoping, not a provider-issued element generation. Same-path,
same-name reuse within one provider remains indistinguishable. Unique connection
names are scoped to one accessibility bus lifetime. A private authenticated
[bus-generation guard](BUS-GENERATION.md) additionally prevents reuse across
replacement connections; application reconnection remains subject to the
[lifecycle limitations](LIFECYCLE-QUALIFICATION.md).
