import unittest
from ordered_oracle import accept_snapshot
class OrderedOracleTests(unittest.TestCase):
    def test_delayed_preedit_snapshot_cannot_replace_completed_key_snapshot(self):
        state={}
        final={'oracle_document':1,'oracle_sequence':5,'oracle_barrier':2,'text':'u306b'}
        old={'oracle_document':1,'oracle_sequence':4,'oracle_barrier':1,'text':'u306'}
        self.assertTrue(accept_snapshot(state,final))
        self.assertFalse(accept_snapshot(state,old));self.assertEqual(state,final)
    def test_old_document_cannot_overwrite_new_document_even_with_later_sequence(self):
        state={'oracle_document':2,'oracle_sequence':1,'text':'new'}
        self.assertFalse(accept_snapshot(state,{'oracle_document':1,'oracle_sequence':999,'text':'old'}))
        self.assertEqual(state['text'],'new')
    def test_later_snapshot_with_real_mutation_is_not_hidden(self):
        state={'oracle_document':1,'oracle_sequence':3,'text':'u306b'}
        self.assertTrue(accept_snapshot(state,{'oracle_document':1,'oracle_sequence':4,'text':'MUTATED'}))
        self.assertEqual(state['text'],'MUTATED')
    def test_invalid_or_duplicate_metadata_does_not_advance_oracle(self):
        state={'oracle_document':1,'oracle_sequence':1,'text':'original'}
        for incoming in ({'text':'bad'},{'oracle_document':True,'oracle_sequence':2},{'oracle_document':1,'oracle_sequence':1,'text':'duplicate'}):
            self.assertFalse(accept_snapshot(state,incoming))
        self.assertEqual(state['text'],'original')
