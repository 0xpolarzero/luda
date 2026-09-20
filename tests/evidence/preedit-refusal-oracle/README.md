# Preedit refusal oracle ordering

Hosted source `9e17932`, matrix run `run-1789895395852047343`, failed
`preedit-preserved-after-refusal`. The original log and relevant records remain
here. Before the refusal, public readback already contained the full `u306b`
preedit, while the captured independent HTTP snapshot still contained `u306`.
The refusal was `IME_COMPOSITION_ACTIVE`, effect `none`, clipboard-change false.
The final retained oracle subsequently contained the exact full text from the
public readback. The failed comparison itself recorded no snapshots, so its
precise value/timing cannot be reconstructed. This does not prove that runtime
input changed the document.

The fixture issued independent fetches for each event and used a threaded HTTP
server that unconditionally replaced state; delayed older snapshots could
replace newer snapshots. Its oracle file was also written outside the state
lock, so the file and in-memory assertion were not necessarily the same sample.
Four deterministic tests reproduce and prevent obsolete-sequence replacement,
cover old-document arrival after reload, reject invalid/duplicate sequence data,
and prove that a genuinely later changed value is still accepted rather than
hidden.

Each document now receives a server-issued generation and each browser snapshot
a sequence. Only increasing generation/sequence pairs update the oracle and
its file, under one lock. A test-only periodic GET receives a requested barrier
number; the application responds with a newly sampled DOM snapshot and that
number. This reads state only: it does not focus, select, type, commit, cancel,
or dispatch synthetic input. Each barrier has a two-second deadline.

Before conflicting input, the independent fresh sample must equal public
readback and include trusted composition start. After the explicit refused
request, a fresh public read and a separate fresh application sample must retain
text, known-active composition, document identity, selection and event tail.
Both samples are retained even on failed equality. A later actual mutation is
not ignored, and no input is retried. This strengthens the original equality
check; it does not replace it with eventual acceptance of an arbitrary value.

The final UID1001 private Xvfb/XFWM/D-Bus owned-browser suite passed in 19.983s,
source unchanged, no owned survivors; Chromium153.0.8010.12 on Ubuntu24.04 ARM64.
`result.json` records exact source hashes and before/after samples. This is one
scoped successful local run, not a new hosted pass or proof that every potential
application race is fixed. No production source changed.
