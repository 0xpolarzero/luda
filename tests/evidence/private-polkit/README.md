# Private system authentication evidence

[Scope and reproduction](../../../docs/PRIVATE-SYSTEM-AUTH-QUALIFICATION.md).
The original attempts are preserved, including setup failures. Attempt1 starts
the real authority and confirms the stock GNOME agent's missing-session blocker.
Attempt2 lacks pkexec's package-postinst setuid mode. Attempts3/4 reject an assumed
`program` detail that polkit does not forward; attempt4 safely cancels that request
without GUI action. Attempt5 succeeds with authoritative sender/action/caller/subject
binding and public GUI Cancel. `final/` is the source-bound reusable runner result,
host before/after hashes, real daemon/caller logs, tool responses and screenshot.
No credentials were supplied, no request was authorized, and no result is promoted
to GNOME or universal privileged-dialog support. Some internal polkit warnings
remain visible. No global policies or accounts were changed.
