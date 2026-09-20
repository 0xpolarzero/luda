# Integrated semantic, workspace and installation changes

At `0dcc8fa`, root tests passed981/982 in39.026seconds with one build-dependency skip. The ordinary desktop account passed972/982 in38.392seconds with that skip, eight unavailable Codex CLI cases and one root-only access case. Both retain unchanged source fingerprint `31fc2ab0af0f06f7f5e52252737285f5a9575629c8826db98fddaa31c099ff36`.

The original private matrix passed native semantic workflows6.350seconds, but its workspace fixture stopped before creating its app because the new artifact directory was not writable by UID1001. That failure remains in original-matrix.json.gz. Creating only the dedicated artifact directory for that account allowed the separate unchanged-source workspace rerun to pass1.555seconds. This is not an all-green original matrix.

Actual root installation under umask077 produced `0.1.0-9e9828aba1cf25bc`. Independent UID1001 isolated imports matched all50 runtime module hashes and the skill, with unchanged installer source hashes. No desktop app was launched by that install proof; it does not establish fresh Mac/Silo onboarding.
