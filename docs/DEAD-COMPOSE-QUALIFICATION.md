# Dead-key and Compose boundary

KEY-10 requires defined support or a clear unsupported response. The existing
keyboard grammar accepts one supported named key with optional modifiers. It
rejects dead-key names and Compose requests with `INVALID_KEY`, `effect=none`,
and guidance to use `desktop_type` for text. This qualification exercises that
refusal through an actual persistent public MCP connection; it adds no API or
runtime behavior.

Run the isolated fixture as the ordinary desktop account:

```sh
.venv/bin/python tests/live_dead_compose.py
```

The harness creates private Xvfb, D-Bus and XDG directories. It installs French
XKB with `compose:ralt` only on that display and independently confirms both
`dead_circumflex` and `Multi_key` have keycodes. An owned GTK TextView writes its
actual text and received press/release events; an independent XQueryKeymap and
XQueryPointer connection checks held input.

The five requests `dead_circumflex`, `dead_acute`, `Multi_key`, `Compose` and
`Compose+apostrophe+e` all returned `INVALID_KEY` with no effect. After each,
widget text and its event log were unchanged, no key or mouse button remained
held, and no sequence continuation was sent. Ordinary semantic insertion of
`é ê œ 日本語 👩🏽‍💻` subsequently matched independent widget state and public text
readback. The configured keymap remained byte-for-byte unchanged by the tools;
the original private map was restored before shutdown.

The successful run records **9/9 assertions**, UID 1001, GTK
3.24.41-4ubuntu1.3, xkb-data 2.41-2ubuntu1.1 and Xvfb
2:21.1.12-1ubuntu1.6. Its unchanged source fingerprint was
`7174548a448c60cab20fcec115fc9892dba11c3afb375a785bbd43564d324c3c`.
Artifacts: `artifacts/dead-compose/attempt-3/`; cleanup found no owned survivors.

Attempts 1 and 2 retain their failed harness restoration assertion: recompiling
an exported XKB map normalized component names and a redundant default mapping,
so textual equality failed although all input/refusal checks passed. The harness
now restores the original rules/model/layout/variant/options through setxkbmap
and verifies the complete exported map. Both earlier private displays were
removed; no shared desktop layout was changed.

This is explicit refusal qualification, not dead-key/Compose sequence support.
It does not test a human's already-pending composition, arbitrary IMEs, every
keyboard layout or secret input. Semantic insertion of the resulting Unicode
text does not establish composition support. No automatic Escape, Return or
sequence completion is used.
