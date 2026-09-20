"""Grade fresh-agent traces independently of model output claims."""
import importlib.util
from pathlib import Path
import sys
import unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
spec=importlib.util.spec_from_file_location('agent_eval',ROOT/'scripts/agent_eval.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class AgentTrace(unittest.TestCase):
    skill=Path('/tmp/task/workspace/.agents/skills/luda/SKILL.md')
    def test_skill_reads_allowed(self):
        self.assertTrue(m.allowed_command("/bin/bash -lc 'cat /tmp/task/workspace/.agents/skills/luda/SKILL.md'",self.skill))
        self.assertTrue(m.allowed_command('cat .agents/skills/luda/SKILL.md',self.skill))
    def test_hidden_reads_and_shell_chaining_refused(self):
        for command in ('cat /tmp/oracle.json','cat .agents/skills/luda/SKILL.md; cat /tmp/oracle.json','python -c "print(1)"'):
            self.assertFalse(m.allowed_command(command,self.skill))
    def test_started_forbidden_command_is_failure_even_without_completion(self):
        result=m.grade_trace([{'type':'item.started','item':{'type':'command_execution','command':'cat /tmp/oracle.json'}}],self.skill)
        self.assertFalse(result['skill_reads_only'])
    def test_non_desktop_tool_and_direct_edit_refused(self):
        result=m.grade_trace([{'type':'item.completed','item':{'type':'mcp_tool_call','server':'other','tool':'read_file'}},{'type':'item.completed','item':{'type':'file_change'}}],self.skill)
        self.assertFalse(result['only_public_desktop_tools']);self.assertFalse(result['no_direct_file_changes'])
    def test_public_tool_and_usage(self):
        result=m.grade_trace([{'type':'item.completed','item':{'type':'mcp_tool_call','server':'luda','tool':'desktop_observe'}},{'type':'turn.completed','usage':{'input_tokens':42}}],self.skill)
        self.assertTrue(result['only_public_desktop_tools']);self.assertEqual(result['usage'],[{'input_tokens':42}])
if __name__=='__main__':unittest.main()
