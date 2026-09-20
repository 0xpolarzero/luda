"""Record failures even when CLI wraps a failed tool as a completed event."""
import importlib.util
import json
from pathlib import Path
import sys
import unittest

scripts=Path(__file__).resolve().parents[1]/'scripts'
sys.path.insert(0,str(scripts))
from agent_locale_eval import tool_failures


def event(value=None,**fields):
    item={'type':'mcp_tool_call','result':{'content':[{'type':'text','text':json.dumps(value)}]},**fields}
    return {'type':'item.completed','item':item}


class AgentLocaleGrading(unittest.TestCase):
    def test_completed_public_error_is_preserved_without_mcp_flag(self):
        failure=event({'ok':False,'code':'TEXT_MISMATCH','effect':'uncertain'})
        self.assertEqual(tool_failures([failure]),[failure['item']])
    def test_transport_error_and_protocol_flag_are_preserved(self):
        transport=event(error={'message':'transport unavailable'})
        protocol=event(result={'isError':True,'content':[]})
        self.assertEqual(tool_failures([transport,protocol]),[transport['item'],protocol['item']])
    def test_success_dispatch_and_started_events_are_not_errors(self):
        success=event({'ok':True,'effect':'dispatched'})
        started=event({'ok':False});started['type']='item.started'
        self.assertEqual(tool_failures([success,started,event('plain text')]),[])

if __name__=='__main__':unittest.main()
