import importlib.util
from pathlib import Path
import sys
import unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
from agent_rich_eval import grade,PREFIX,INSERT,SUFFIX,MIDDLE


class RichAgentOracleTests(unittest.TestCase):
    def saved(self):
        parts=(PREFIX+INSERT+SUFFIX).split('\n')
        nodes=[{'type':'paragraph','content':[{'type':'text','text':PREFIX,'marks':[{'type':'strong'}]},{'type':'text','text':parts[0][len(PREFIX):]}]},
               {'type':'paragraph','content':[{'type':'text','text':parts[1]}]},
               {'type':'paragraph','content':[{'type':'text','text':SUFFIX,'marks':[{'type':'em'}]}]}]
        return {'model':{'type':'doc','content':nodes},'paragraphs':parts,'events':[{'type':'paste','trusted':True}]}
    def test_exact_actual_model_and_marks(self):
        self.assertEqual((len(PREFIX),len(PREFIX+MIDDLE)),(10,19));self.assertTrue(all(grade(self.saved()).values()))
    def test_text_only_oracle_cannot_hide_lost_formatting(self):
        saved=self.saved();saved['model']['content'][0]['content'][0].pop('marks');self.assertFalse(grade(saved)['prefix_marks']);self.assertTrue(grade(saved)['exact_text'])
    def test_rendered_oracle_must_match_independent_model(self):
        saved=self.saved();saved['paragraphs'][1]='lost tab';self.assertFalse(grade(saved)['exact_paragraphs'])
