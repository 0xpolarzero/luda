# Offline installed runtime evidence

See [the scoped qualification report](../../../docs/OFFLINE-STARTUP-QUALIFICATION.md).
`run.py` sets up a private network namespace as root, then runs `probe.py` through
the installed interpreter as the explicitly selected ordinary desktop account.
Neither file modifies host networking. No network installation is performed.

`result/` retains the final successful run; `first-attempt.json` retains the earlier
IPv6 errno-precondition failure. Runtime and fixture source identities are separate:
the pinned installed release is intentionally not described as the latest checkout.
