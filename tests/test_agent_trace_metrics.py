import base64
import importlib.util
import json
from pathlib import Path
import unittest
spec=importlib.util.spec_from_file_location('agent_trace_metrics',Path(__file__).resolve().parents[1]/'scripts/agent_trace_metrics.py')
trace=importlib.util.module_from_spec(spec);spec.loader.exec_module(trace)

class AgentTraceMetricsTests(unittest.TestCase):
    def event(self,tool,payload,**extra):
        content=[{'type':'text','text':json.dumps(payload,ensure_ascii=False)},*extra.get('content',[])]
        return {'type':'item.completed','item':{'id':'1','type':'mcp_tool_call','tool':tool,'result':{'content':content}}}
    def test_started_events_are_not_double_counted(self):
        event=self.event('desktop_observe',{'elapsed_ms':12});started={**event,'type':'item.started'}
        result=trace.metrics([started,event]);self.assertEqual(result['completed_calls'],1);self.assertEqual(result['reported_backend_elapsed_ms_sum'],12)
    def test_missing_failure_timing_is_not_assumed_zero(self):
        result=trace.metrics([self.event('desktop_click',{'ok':False,'code':'STALE_TARGET'})])
        self.assertEqual(result['calls_with_backend_elapsed_ms'],0);self.assertEqual(len(result['calls_without_backend_elapsed_ms']),1)
    def test_bytes_are_not_unicode_characters_or_tokens(self):
        event=self.event('desktop_inspect',{'nodes':[{'name':'日本語','states':['showing']}],'elapsed_ms':3})
        result=trace.metrics([event]);expected=len(event['item']['result']['content'][0]['text'].encode())
        self.assertEqual(result['response_content_volumes']['desktop_inspect']['text_utf8_bytes'],expected)
        self.assertEqual(result['inspections'][0]['showing_nodes'],1)
    def test_screenshot_encoded_and_decoded_volumes(self):
        event=self.event('desktop_observe',{},content=[{'type':'image','data':base64.b64encode(b'12345').decode()}])
        volume=trace.metrics([event])['response_content_volumes']['desktop_observe']
        self.assertEqual((volume['images'],volume['image_base64_characters'],volume['decoded_image_bytes']),(1,8,5))
