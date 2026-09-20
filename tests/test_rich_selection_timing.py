import unittest
from unittest.mock import Mock,patch
from test_browser_rich import value
from luda._browser_worker import Worker,Refused

class RichSelectionTimingTests(unittest.TestCase):
    def test_whole_end_and_empty_ranges_preserve_native_route(self):
        for text,start,end,key in [('abc',0,3,'a'),('abc',3,3,'End'),('',0,0,'End')]:
            before=value(text);after=value(text);after.update(start=start,end=end)
            bridge=Mock();w=Worker('unused');w.protocol=Mock();w.snapshot=Mock(side_effect=[({'bridge':bridge},before),({'bridge':bridge},after)])
            result=w.select('field',start,end)
            self.assertEqual(result['effect'],'verified');bridge.evaluate.assert_not_called();bridge.evaluate_handle.assert_not_called()
            self.assertEqual([call.args[1]['key'] for call in w.protocol.send.call_args_list],[key,key])

    def test_middle_range_still_uses_model_bound_dom_mapping(self):
        before=value('abc');after=value('abc');after.update(start=1,end=2)
        bridge=Mock();bridge.evaluate.side_effect=[True,{}]
        w=Worker('unused');w.protocol=Mock();w.snapshot=Mock(side_effect=[({'bridge':bridge},before),({'bridge':bridge},before),({'bridge':bridge},after)])
        result=w.select('field',1,2)
        self.assertEqual((result['start_offset'],result['end_offset']),(1,2));w.protocol.send.assert_not_called()
        self.assertEqual(bridge.evaluate.call_count,2);bridge.evaluate_handle.return_value.dispose.assert_called_once()

    def test_selection_sync_diagnostic_is_fixed_and_no_text(self):
        before=value('synthetic text must not leak');w=Worker('unused');w.protocol=Mock();w.snapshot=Mock(return_value=({},before))
        with patch('luda._browser_worker.time.monotonic',side_effect=[0,1]):
            with self.assertRaises(Refused) as exc:w.select('field',0,len(before['text']))
        self.assertEqual(exc.exception.code,'SELECTION_UNVERIFIED');self.assertEqual(exc.exception.stage,'selection_sync')
        self.assertNotIn(before['text'],str(exc.exception))

    def test_post_content_caret_diagnostic_is_distinct(self):
        before=value('');after=value('x');after.update(start=0,end=0)
        w=Worker('unused');w.protocol=Mock();w.snapshot=Mock(side_effect=[({},before),({},before),({},after)])
        with self.assertRaises(Refused) as exc:w.rich_type('field','x','insert',None,before)
        self.assertEqual(exc.exception.stage,'caret_readback');self.assertEqual(w.effect,'uncertain')

    def test_public_protocol_projects_only_fixed_diagnostic_stages(self):
        import json,subprocess,sys
        from luda.browser import OwnedBrowser
        from luda.common import DesktopError
        for stage in ('selection_sync','caret_readback','SYNTHETIC_PRIVATE_TEXT',{'secret':'SYNTHETIC_PRIVATE_TEXT'}):
            response={'error':'SELECTION_UNVERIFIED','effect':'uncertain','provider_stage':stage}
            process=subprocess.Popen([sys.executable,'-c','import sys;sys.stdin.readline();print(sys.argv[1],flush=True);sys.stdin.read()',json.dumps(response)],stdin=subprocess.PIPE,stdout=subprocess.PIPE)
            owner=OwnedBrowser(None);owner.process=process
            try:
                with self.assertRaises(DesktopError) as caught:owner.request('type',token='fixture')
                expected=stage if isinstance(stage,str) and stage in ('selection_sync','caret_readback') else None
                self.assertEqual(caught.exception.details.get('provider_stage'),expected)
                self.assertNotIn('SYNTHETIC_PRIVATE_TEXT',str(caught.exception.details)+str(caught.exception))
            finally:
                process.stdin.close();process.wait(timeout=2);process.stdout.close()
