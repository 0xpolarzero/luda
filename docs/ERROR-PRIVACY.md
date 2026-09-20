# Unexpected error privacy

Unexpected backend exception messages can contain submitted text, application contents or a provider's diagnostic echo. The MCP operation boundary returns a fixed `INTERNAL_ERROR` recovery hint and operation ID instead of exception text or repr. The effect remains uncertain: a failure is not proof that no input occurred. Recent-operation history contains metadata only and can be correlated using that operation ID. The operation gate is released, while any independent unfinished input-recovery owner remains quarantined.

Structured `DesktopError` messages and details retain their existing actionable diagnostics. Their producers remain responsible for safe contents. Protected input already sanitizes worker transport/provider errors, refuses ordinary protected-field readback, and does not fall back to clipboard verification. The existing protocol validator also omits submitted values and unknown parameter names from schema errors. This change closes the unexpected-exception path without globally hiding useful typed errors.

`tests/test_error_redaction.py` demonstrates an unexpected protected-input exception, an injected worker decode exception, an exception whose string formatter itself raises, metadata/stream redaction, typed diagnostic preservation, operation-gate recovery and retained quarantine ownership. Four of the five baseline tests failed. All five pass after the fix; the full unit suite passed 551 tests on this snapshot. These are deterministic boundary regressions, not proof that every application or operating-system log excludes sensitive material.

Backend error envelopes now include `elapsed_ms`, measured from the same monotonic
start as successful responses. Typed failures, unexpected redacted exceptions and
busy rejection retain their operation ID and effect contract. The measurement is
metadata only and does not add exception text or input contents. Recent history
also retains timing; its final accounting can be slightly later than response
construction. Protocol/schema failures before backend execution do not imply a
measured backend duration.

This closes the timing omission observed in the first-attempt file-manager agent
trace, where two backend errors lacked duration fields. Historical trace metrics
remain unchanged. Deterministic tests cover typed/unexpected failures, privacy,
history correlation and busy rejection without touching the backend; the actual
MCP error assertion also checks a nonnegative integer timing field.
