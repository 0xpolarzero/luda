# Control and cancellation recovery review

Three concrete lifecycle failures now have deterministic regression tests.

A cancelled request used to clear a shared recovery flag when its worker
finished, even if a different cancelled worker remained active. A later
request rejected as BUSY could therefore make `desktop_status.recovering`
false prematurely. The operation gate still prevented concurrent mutation;
the incorrect claim was recovery status. Recovery now tracks each cancelled
worker separately and removes only that worker's ownership on completion.
Repeated completion cleanup is idempotent. Tests cover both overlapping
cancellation and a worker that exceeds the two-second cleanup wait, with
new operations rejected until its eventual completion.

Pending keyboard guardians also retain their own recovery ownership before
a tool can return `KEYBOARD_CLEANUP_PENDING`. The server registers the same
thread-safe retain/release callbacks with the keyboard layer. A real child
process integration test verifies pending keyboard cleanup blocks pointer
operations too, and guardian completion cannot clear another operation's
recovery ownership. Unproven cleanup remains quarantined.

Control commands previously fetched a backend and then read or updated its
pause state outside the backend-swap lock. A concurrent reconnect could
switch displays before the old display's pause completed. Control commands
now linearize their selected backend and state operation with reconnect's
swap. A thread-barrier test holds the pause write and verifies reconnect
cannot swap early; another confirms control status remains available while
an ordinary operation holds the separate operation gate.

Pause-state reads previously used a blocking file open and unbounded JSON
read. A FIFO substituted for the state file could hang a checkpoint or the
control tool indefinitely. Reads now use nonblocking descriptors and require
an account-owned, mode-0600, singly linked regular file of at most 4096 bytes.
The same file checks protect the arbitration lock. Invalid schemas, excessive
size, booleans/negative revisions and nonfinite timestamps fail closed as
`CONTROL_UNAVAILABLE`. Missing state preserves the documented unpaused
initial default. Failed pause/resume writes preserve prior committed state
and return a redacted actionable error.

`tests/test_lifecycle_races.py` schedules real worker threads with explicit
barriers; it does not rely on random cancellation timing. The FIFO regression
runs in a separate process with a hard test timeout so a regression cannot
hang the test runner. State-integrity tests also cover oversized files,
hard links, public permissions, failed fsync, lock cleanup and subsequent
recovery. Existing reconnect tests still verify candidate failure preserves
the old backend, a successful swap retires it, identity changes are rejected
and repeated swaps do not accumulate exit handlers.

These changes do not turn advisory pause into an operating-system input
lock or promise to interrupt every blocked kernel syscall. Already dispatched
input remains possible after cancellation, and uncertain operations must be
inspected rather than automatically replayed. Reconnect and admission were
reviewed without broad replacement; their existing transaction and identity
contracts remain in force.
