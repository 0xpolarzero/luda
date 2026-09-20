# Native KeePassXC password-manager popup

AUTH-03 asks that password-manager UI target the correct application/menu and
preserve user intent. `tests/live_password_manager.py` uses actual distro
KeePassXC **2.7.6+dfsg.1-1build3**, a disposable encrypted vault, and two distinct
synthetic entries. It does not substitute a generic password field for the app.

Install `keepassxc` as a **test-only** Ubuntu dependency; it is not added to Luda's
runtime installer. Run from a locked-dependency Luda environment as an ordinary
account:

```bash
.venv/bin/python tests/live_password_manager.py
```

The suite creates private XDG configuration before D-Bus, a private Xvfb/Xfwm
session, the actual manager and an owned GTK decoy input window. Its 75-second
outer bound and tagged cleanup do not affect a user's password manager or vault.
Artifacts use a unique `artifacts/password-manager/<time_ns>/` directory.
All credentials and documents in that directory are synthetic test data.

## Setup versus tested behavior

`keepassxc-cli` creates the vault and its two entries before GUI testing. The app
is unlocked at startup using its documented `--pw-stdin` option with a synthetic
master password. This setup does **not** qualify GUI unlocking, protected-field
editing, browser autofill, extensions, or secret input provider compatibility.
No actual user vault, browser profile or credential is read. Passwords are never
sent as command-line arguments.

The tested UI is driven through public **Desktop methods**, not private Qt calls
or DOM mutation. This suite does not separately qualify MCP transport. Read-only
`xclip` and encrypted-file hashes provide independent effect oracles; a fixture
clipboard owner establishes the initial sentinel without driving application UI.

The two stored entries are `Synthetic login` / username `synthetic-user`, and
`A different account` / username `wrong-entry-sentinel`. Public Ctrl+F and paste
select the intended entry through visible search. The captured screenshot shows
one search result and its username. The final clipboard bytes distinguish the
chosen account from the other stored account.

## Actual result

Run `1789879172082720200` passed seven checks on source base `71690ff`,
fingerprint `1524922e58bf7880e8444236b7b3e6f01ad5f5e181484e5bf3a6519e890d0ef0`.
Source before/after matched, no tagged processes survived, and GUI UID was 1001
on Ubuntu 24.04 ARM64. The selected-entry and native-menu screenshots were
visually reviewed.

- Invoking the actual Entries menu exposes a native popup with KeePassXC's PID,
  transient owner and observed generation. `Copy Username` is an observed
  semantic menu item from that same application.
- Supplying the decoy window as owner for that popup is refused with
  `STALE_TARGET`, effect `none`, before pointer input.
- Escape cancels the menu. Clipboard sentinel and encrypted vault bytes remain
  unchanged.
- Invoking the now-dismissed menu handle is refused with `NOT_INTERACTABLE`,
  effect `none`. Clipboard and decoy text remain unchanged.
- A fresh explicit menu observation followed by `Copy Username` reports dispatch;
  independently read clipboard bytes equal `synthetic-user`, not the second
  entry's `wrong-entry-sentinel`.
- The vault hash remains unchanged and the decoy text is empty: the operation
  copied the requested username without editing the vault, auto-typing into a
  target or submitting anything to a website.

The final run's unchanged vault SHA-256 was
`301df0e697be6874efe424b5cedf6b541b4e12ea08d6d4c3fe108556f3e9cd03`.
This is a synthetic artifact identity, not a user-vault fingerprint.

## Preserved attempts and limits

An initial setup probe requested a 10 ms decryption target; the real CLI rejected
it because its supported minimum is 100 ms. That setup failure is retained.
A preliminary single-entry native-menu run `1789879119623233258` passed before
the two-entry selection oracle was added. Full initial accessibility inspection
included many hidden panels and truncated at 500 nodes; the final workflow uses
showing-state-filtered inspections and exact named menu actions. A truncated tree
is not presented as a complete inventory of vault contents.

This qualifies a bounded native entry-menu workflow, not every password-manager
popup, GUI unlock, auto-type target match, browser-extension permission prompt,
credential submission, clipboard expiry behavior or secret-provider support.
No protected-input result is inferred from successful username copying. No runtime
change was indicated; AUTH-03 remains release-unqualified pending the broader
acceptance matrix. The standalone suite is not silently added to ordinary desktop
startup or a mandatory CI package installation.
