import unittest
from permission_oracle import PermissionOracle

class PermissionReports(unittest.TestCase):
    def test_late_partial_cannot_erase_independent_callback(self):
        oracle=PermissionOracle()
        completed={'document':'owned-page','sequence':4,'permission':'denied','error':1,'requests':1,'successes':0}
        oracle.accept(completed)
        self.assertFalse(oracle.accept(dict(completed,sequence=3,error=None)))
        self.assertEqual(oracle.state,completed)
        self.assertEqual([r['applied'] for r in oracle.reports],[True,False])
        self.assertIsNone(oracle.reports[1]['snapshot']['error'])

    def test_missing_callback_remains_failure_not_inferred(self):
        oracle=PermissionOracle()
        oracle.accept({'document':'owned-page','sequence':3,'permission':'denied','error':None})
        self.assertIsNone(oracle.state['error'])
        self.assertFalse(oracle.accept({'document':'owned-page','sequence':2,'permission':'prompt','error':1}))
        self.assertIsNone(oracle.state['error'])

    def test_invalid_sequence_is_not_authority(self):
        for sequence in (None,True,0,-1,'9'):
            with self.subTest(sequence=sequence),self.assertRaises(ValueError):
                PermissionOracle().accept({'document':'owned-page','sequence':sequence})

    def test_other_document_cannot_replace_selected_page(self):
        oracle=PermissionOracle()
        original={'document':'owned-page','sequence':2,'permission':'prompt','error':None}
        oracle.accept(original)
        self.assertFalse(oracle.accept({'document':'replacement','sequence':99,'permission':'denied','error':1}))
        self.assertEqual(oracle.state,original)
