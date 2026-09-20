"""Evidence classification only: failed probes remain failed, catalog stays untouched."""
import json
from pathlib import Path

WORKFLOWS={
 'AUTH-04':(['digit-key-otp-us','digit-key-otp-fr'],'Visible digit-only OTP on US/French layouts; no added clipboard copy or complete value in captured responses/artifacts, not universal retention erasure.'),
 'AUTH-05':(['expiry-recovery-observes-before-new-input'],'Old semantic target refusal, then fresh login-transition inspection with no unintended action/submission; stale screenshot route remains unsafe.'),
 'AUTH-06':(['popup-origin-session-identified-before-approval','local-popup-return-to-intended-window','returned-app-session-visible'],'Synthetic loopback browser-chrome origin and visible session identification before approval, then intended app/session readback; no real OAuth protocol qualification.'),
 'AUTH-07':(['blocked-credential-explicit-limitation'],'Real password-field paste prevention observed independently; raw paste reports dispatch only and explicit protected input refuses unsupported provider without mutation.'),
 'AUTH-10':(['human-presence-exposed-not-completed'],'Synthetic human-presence notice exposed with app still waiting; not generic CAPTCHA detection.'),
}
DIAGNOSTICS={
 'ordinary-otp-not-secret-storage':('unsupported_for_nonretaining_input','Ordinary clipboard route retains the OTP; the scoped key route is tested separately.'),
 'browser-protected-otp-support':('unsupported_provider','Native protected input remains unsupported here and relevant to AUTH-01, not proof of clipboard-blocked AUTH-07.'),
 'oauth-origin-session-attestation':('historical_out_of_scope_assertion','Cryptographic attestation exceeded the catalog; actual GUI origin/session identification is required separately.'),
 'old-screenshot-after-same-window-replacement':('unsafe_content_reuse','Actual wrong-intent activation remains a content-freshness limitation, not a fixed behavior.'),
}

SUPPORTING_PROBES=('unmasked-otp-secret-path-refused','ordinary-otp-leading-zeros','explicit-otp-submit-clears-fixture','expired-session-old-element-refused','expiry-visible-in-fresh-observation')
EXPECTED_PROBES=tuple(dict.fromkeys([name for names,_ in WORKFLOWS.values() for name in names]+list(DIAGNOSTICS)+list(SUPPORTING_PROBES)))

def report(records):
 catalog=json.loads((Path(__file__).resolve().parents[1]/'docs/requirements.json').read_text())
 def cases(value):
  if isinstance(value,dict):
   if 'id' in value and 'acceptance' in value:yield value
   for child in value.values():yield from cases(child)
  elif isinstance(value,list):
   for child in value:yield from cases(child)
 criteria={row['id']:row for row in cases(catalog)}
 by_name={row['case']:row for row in records}
 duplicates=len(by_name)!=len(records)
 workflows=[]
 for requirement,(names,scope) in WORKFLOWS.items():
  missing=[name for name in names if name not in by_name]
  outcome='not_run' if missing else 'passed' if all(by_name[name]['passed'] for name in names) else 'failed'
  workflows.append(dict(requirement=requirement,acceptance=criteria[requirement]['acceptance'],catalog_qualification=criteria[requirement]['qualification'],scope=scope,probe_ids=names,outcome=outcome,missing_probes=missing))
 diagnostics=[dict(row,classification=DIAGNOSTICS[row['case']][0],reason=DIAGNOSTICS[row['case']][1]) for row in records if row['case'] in DIAGNOSTICS]
 unexpected_failures=[row['case'] for row in records if not row['passed'] and row['case'] not in DIAGNOSTICS]
 missing_records=[name for name in EXPECTED_PROBES if name not in by_name]
 okay=not missing_records and not duplicates and not unexpected_failures and all(row['outcome']=='passed' for row in workflows)
 return dict(cases=records,required_workflows=workflows,route_diagnostics=diagnostics,
             probe_summary=dict(total=len(records),passed=sum(bool(r['passed']) for r in records),failed=sum(not r['passed'] for r in records)),
             scope_limits={'AUTH-07':'Synthetic browser password field with a real paste-event blocker; supported result is an explicit provider limitation, not successful credential entry.','retention':'Caller transcripts, per-key arguments, destination memory and external listeners are not erased or qualified.','OAuth':'GUI identification only; no cryptographic attestation or real-provider protocol qualification.'},
             required_workflows_passed=okay,missing_probe_records=missing_records,duplicate_probe_names=duplicates,unexpected_failed_probes=unexpected_failures,
             exit_policy='Nonzero for missing/failed required workflow, unexpected failed probe, duplicate/missing probe record or harness failure. Classified diagnostics retain original passed values and do not become supported capabilities.')
