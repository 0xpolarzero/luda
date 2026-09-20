# Deterministic stopped-worker fixture

Hosted desktop run35508744339 (source301a535) timed out after120seconds in input-generation; its suite log was empty. Other16 suites passed. Earlier source830a3c4 passed the complete hosted desktop job. The original timeout does not identify its blocked call and is retained, not diagnosed by a later pass.

The fixture previously sent SIGSTOP asynchronously to a worker between key presses. That can stop it inside XGrabServer, blocking the fixture's next X query. It now instruments only its disposable worker to stop immediately after the first production press_target returns, when XUngrabServer/XSync have completed. The real production guardian, planning, native key-down, server replacement and cleanup behavior remain exercised. No runtime hook or production behavior changed. Remaining guardian proof reads and command calls are bounded.

Sixteen focused contracts passed, including actual-pipe partial/EOF/deadline tests. The real private X-server replacement workflow passed, and the deliberately stopped final Xvfb cleanup case also passed with TERM-to-KILL escalation. Both prove replacement key/button/pointer preservation and generation-aware recovery. This removes a concrete fixture deadlock hazard; it does not establish the exact cause of the historical uninstrumented timeout.
