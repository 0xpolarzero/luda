import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from agent_hard_break_eval import grade,PREFIX,INSERT,SUFFIX
class Oracle(unittest.TestCase):
 def saved(self):
  content=[{'type':'text','text':PREFIX,'marks':[{'type':'strong'}]}]
  for i,line in enumerate(INSERT.split('\n')):
   if i:content.append({'type':'hard_break'})
   content.append({'type':'text','text':line})
  content.append({'type':'text','text':SUFFIX,'marks':[{'type':'em'}]})
  return {'model':{'type':'doc','content':[{'type':'paragraph','content':content}]},'modelCaretCodePoints':len(PREFIX+INSERT)}
 def test_exact_model_marks_and_caret(self):self.assertTrue(all(grade(self.saved()).values()))
 def test_same_plaintext_paragraphs_fail_structure(self):
  value=self.saved();parts=[[]]
  for node in value['model']['content'][0]['content']:
   if node['type']=='hard_break':parts.append([])
   else:parts[-1].append(node)
  value['model']['content']=[{'type':'paragraph','content':part} for part in parts]
  self.assertTrue(grade(value)['exact_logical_text']);self.assertFalse(grade(value)['one_paragraph_two_hard_breaks'])
 def test_lost_marks_cannot_hide_behind_exact_text(self):
  value=self.saved();value['model']['content'][0]['content'][0].pop('marks')
  self.assertTrue(grade(value)['exact_logical_text']);self.assertFalse(grade(value)['prefix_marks'])
