import unittest
from auth_report import report,WORKFLOWS,DIAGNOSTICS,EXPECTED_PROBES

class EvidenceClassification(unittest.TestCase):
 def records(self):return [{'case':name,'passed':True} for name in EXPECTED_PROBES]
 def test_missing_required_evidence_never_passes(self):
  result=report([r for r in self.records() if r['case']!='digit-key-otp-us']);self.assertFalse(result['required_workflows_passed']);self.assertTrue(any(w['outcome']=='not_run' for w in result['required_workflows']))
 def test_failed_required_probe_never_passes(self):
  rows=self.records();rows[0]['passed']=False;self.assertFalse(report(rows)['required_workflows_passed'])
 def test_failed_diagnostics_remain_false_and_visible(self):
  rows=[dict(r,passed=False,measured='retained') if r['case'] in DIAGNOSTICS else r for r in self.records()]
  result=report(rows);self.assertTrue(result['required_workflows_passed']);self.assertEqual(result['cases'],rows);self.assertEqual(result['probe_summary']['failed'],4)
  self.assertTrue(all(not d['passed'] and d['measured']=='retained' for d in result['route_diagnostics']))
  self.assertTrue(all(w['catalog_qualification']=='unqualified' for w in result['required_workflows']))
 def test_omitted_diagnostic_cannot_disappear_into_green(self):
  result=report([r for r in self.records() if r['case']!='old-screenshot-after-same-window-replacement']);self.assertFalse(result['required_workflows_passed']);self.assertEqual(result['missing_probe_records'],['old-screenshot-after-same-window-replacement'])
 def test_unclassified_failure_is_not_hidden(self):
  result=report(self.records()+[{'case':'new-failure','passed':False}]);self.assertFalse(result['required_workflows_passed']);self.assertEqual(result['unexpected_failed_probes'],['new-failure'])
 def test_duplicate_probe_cannot_replace_earlier_failure(self):
  rows=self.records();result=report([dict(rows[0],passed=False),*rows]);self.assertTrue(result['duplicate_probe_names']);self.assertFalse(result['required_workflows_passed'])

if __name__=='__main__':unittest.main()
