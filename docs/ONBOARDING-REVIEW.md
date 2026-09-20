# Fresh guest onboarding review

## Corrected concrete problems

- Root-owned `/opt/luda` is checked against the calling UID for every management
  action. The previous quickstart used `sudo` to install, then omitted it for
  doctor/config. A disposable root-owned prefix invoked as `desktop`
  reproduced exit 1 with the ownership diagnostic. Documentation now consistently
  runs management as the prefix owner; GUI access still drops privileges.
- Local configuration is for Codex running inside the guest. The Mac/SSH example
  now explicitly requests remote placement. Generated README text distinguishes
  where to merge each fragment and says it does not create an SSH connection.
- Plugin registration belongs to the Codex profile owner, not automatically root
  or the guest account. Host registration requires a host-readable marketplace;
  the guest's `/tmp` path and plugin registry are not assumed shared.
- The plugin builder copies this checkout's skill, while its launcher uses the
  installed current runtime. Documentation now requires matching source and
  explains that runtime updates do not refresh cached plugin skills.

Nineteen installer unit tests passed, including local/remote generated instruction
assertions. No actual user agent configuration or plugin registry was changed.

## Deliverables versus external acceptance

The remaining integration deliverable is a Linux-supported lifecycle that installs
Luda with the GUI, generates/registers the correct executor configuration and skill
without overwriting unrelated settings, and presents desktop/tool readiness
separately. Its exact entry points must be identified in Linux source before an
adapter is implemented. The existing guest commands are building blocks, not that
completed product integration.

External acceptance then needs fresh ARM64/AMD64 Linux environment provisioning, actual
Mac Codex profile/executor placement and discovery, an owned GUI task visible to
the human viewer, upgrade preservation and reconnect. Guest tests and local CLI
registration cannot establish those outcomes. A host-facing plugin marketplace
or distribution workflow also needs an explicit supported delivery choice; a
local temporary marketplace is only a test mechanism.

Official documentation checked during this review confirms
[remote stdio placement](https://learn.chatgpt.com/docs/extend/mcp?surface=cli),
[local skill discovery scopes](https://learn.chatgpt.com/docs/build-skills), and
[plugin-scoped policy](https://developers.openai.com/plugins/build/plugins).
Those configuration contracts do not establish that a particular Linux/Mac
executor discovers a guest installation. The supported fresh-host workflow
remains an acceptance task, not an inferred pass.
