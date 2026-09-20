# Permission denial: independent HTTP oracle ordering

Hosted run [35505335100](https://github.com/0xpolarzero/luda/actions/runs/35505335100), source `aef930b`, failed the independent denial/callback assertion. The actual deny invocation returned `dispatched`, `accepted=true` after 322 ms. The last oracle reported `permission="denied"`, `error=null`, one trusted request and zero successes. Original log/result/assertions/oracle are retained unedited. There was no report history or event sequence, so the missing callback cannot be attributed conclusively to transport ordering, browser timing or another cause. A later hosted pass does not explain it.

A concrete fixture defect was found: page permission-change and geolocation callbacks each sent an asynchronous full-state POST; the threaded receiver blindly replaced state in arrival order. Thus an older `denied/error=null` snapshot could erase an already received `denied/error=1` snapshot. The correction attaches a page-generated document UUID and increasing report sequence. The receiver binds to the first document and accepts only its increasing sequences. It retains every received snapshot with application decision and monotonic reception time. It does not infer a missing callback or combine incompatible snapshots. Replacement documents are refused rather than silently resetting the oracle. The generic `ordered_oracle.py` accepts increasing document numbers; this stricter single-document test deliberately does not adopt that navigation policy.

Four units prove reverse arrival, absence of callback remaining absent, invalid sequence refusal and replacement-document refusal. The real private ordinary-UID Chromium fixture also deliberately delays the partial terminal report until the complete report has been received (bounded by the existing five seconds). This affects observation delivery only: the page still calls real geolocation, public MCP invokes the real browser denial button once, and no permission-grant API, callback setter or input retry is used. The original five-second success predicate is unchanged. A new assertion requires the stale report to have arrived and been rejected before checking visible denial status.

Two scoped private runs are retained. Prototype `1789901608980551234` passed in 4.728 s using a fixed 300 ms transport delay. Final `1789901644488885084` passed in 4.634 s using the bounded completion event to make reverse arrival independent of that delay. Both show report order 1,2,4,3; snapshot4 proves denied/error1 and late snapshot3 has error=null and is rejected. Both source inventories remained unchanged during their runs. The final trace includes actual public readback of denied status and clean MCP exit. This demonstrates the ordering fix, not the historical failure's cause or universal browser permission behavior.

Run `PYTHONPATH=tests .venv/bin/python -m unittest test_permission_oracle`. To exercise the actual isolated browser:

```sh
runuser -u silo-desktop -- .venv/bin/python scripts/qualification_matrix.py \
  --suites browser-permission --executable /absolute/trusted/chrome
```

Use a worktree with `artifacts` writable by that account. The matrix provisions a private desktop; no host/user permission settings are modified. No production source changed. Evidence contains authored loopback fixture data only; gzip mtime is zero.
