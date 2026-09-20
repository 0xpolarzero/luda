"""Provider preflight and exact readback contracts without a browser dependency."""
import unittest
from unittest.mock import Mock
from luda._browser_worker import Worker,Refused
from luda.browser import OwnedBrowser
from luda.common import DesktopError


def snapshot(text='',start=0,end=0):
    return {'text':text,'start':start,'end':end,'tag':'TEXTAREA','focused':True,'direction':'forward','composition':{'known':True,'active':False}}


class OwnedBrowserTests(unittest.TestCase):
    def worker(self):
        w=Worker('unused');w.protocol=Mock();w.page=Mock();w.page.evaluate.return_value=True;return w

    def test_exact_unicode_insert_uses_native_input_and_exact_value(self):
        w=self.worker();old=snapshot('A😀B',1,2);new=snapshot('A日本\nB',4,4)
        w.snapshot=Mock(side_effect=[({},old),({},old),({},new)])
        result=w.type('t','日本\n','insert')
        self.assertTrue(result['exact_match']);self.assertEqual(result['actual_characters'],5)
        w.protocol.send.assert_called_once_with('Input.insertText',{'text':'日本\n'})

    def test_preedit_refusal_precedes_focus_or_input(self):
        for code in ('IME_COMPOSITION_ACTIVE','COMPOSITION_UNKNOWN','PROTECTED_FIELD','STALE_TARGET'):
            with self.subTest(code=code):
                w=self.worker();w.snapshot=Mock(side_effect=Refused(code));w.focus=Mock()
                with self.assertRaises(Refused):w.type('t','input','replace')
                w.focus.assert_not_called();w.protocol.send.assert_not_called();self.assertEqual(w.effect,'none')

    def test_single_line_rejects_multiline_before_input(self):
        w=self.worker();before=snapshot();before['tag']='INPUT';w.snapshot=Mock(return_value=({},before))
        with self.assertRaises(Refused) as caught:w.type('t','a\nb','insert')
        self.assertEqual(caught.exception.code,'UNSUPPORTED_TEXT');w.protocol.send.assert_not_called()

    def test_focus_changed_after_dispatch_is_uncertain_and_never_replayed(self):
        w=self.worker();before=snapshot();w.snapshot=Mock(side_effect=[({},before),({},before),Refused('FOCUS_CHANGED')])
        with self.assertRaises(Refused):w.type('t','one request','insert')
        self.assertEqual(w.effect,'uncertain');self.assertEqual(w.protocol.send.call_count,1)

    def test_invalid_lifetime_and_url_never_launch(self):
        for url,lifetime in [('https://example.invalid','persistent'),('https://user:secret@example.invalid','temporary_session'),('file:///tmp/file','temporary_session')]:
            with self.subTest(url=url):
                owner=OwnedBrowser(None)
                with self.assertRaises(DesktopError) as caught:owner.open(url,lifetime)
                self.assertEqual(caught.exception.code,'INVALID_ARGUMENT');self.assertIsNone(owner.process)

    def test_read_limit_keeps_full_codepoint_count(self):
        w=self.worker();w.snapshot=Mock(return_value=({},snapshot('A😀B',2,2)))
        result=w.read('t',2)
        self.assertEqual(result['text'],'A😀');self.assertEqual(result['characters'],3)
        self.assertTrue(result['truncated']);self.assertEqual(result['caret_offset'],2)


class OwnedBrowserSchemaTests(unittest.IsolatedAsyncioTestCase):
    async def test_temporary_lifetime_is_required_and_arbitrary_options_refused(self):
        from unittest.mock import AsyncMock,patch
        from luda.server import mcp
        import json
        with patch('luda.server.execute_async',new_callable=AsyncMock) as dispatch:
            for arguments in ({'url':'https://example.invalid'}, {'url':'https://example.invalid','lifetime':'persistent'}, {'url':'https://example.invalid','lifetime':'temporary_session','profile':'private-profile'}, {'url':'https://example.invalid','lifetime':'temporary_session','script':'private-script'}):
                response=await mcp.call_tool('desktop_open_browser',arguments)
                self.assertTrue(response.isError)
                text=response.content[0].text
                self.assertEqual(json.loads(text)['code'],'INVALID_ARGUMENT')
                self.assertNotIn('private-profile',text);self.assertNotIn('private-script',text)
            dispatch.assert_not_called()


class OwnedBrowserReconnectTests(unittest.TestCase):
    def test_reconnect_reports_unconfirmed_old_browser_cleanup(self):
        from contextlib import contextmanager
        import json
        from unittest.mock import patch
        from luda import server
        old=Mock();old.browser.process=object();new=Mock()
        @contextmanager
        def prepared(*args):yield new,{'effect':'verified','reconnected':True}
        with patch.object(server,'backend',old),patch.object(server,'prepare_reconnect',prepared),patch.object(server.atexit,'register'),patch.object(server.atexit,'unregister'):
            response=server.execute('reconnect',None)
            value=json.loads(response.content[0].text)
            self.assertFalse(response.isError,value)
            self.assertEqual(value['effect'],'uncertain')
            self.assertEqual(value['browser_cleanup'],'unconfirmed')
            self.assertIs(server.backend,new)
            old.close.assert_called_once()


class BrowserGraphemeBoundaryTests(unittest.TestCase):
    def test_boundary_refusal_precedes_focus_selection_and_input(self):
        for available in (False,None):
            w=Worker('unused');w.page=Mock();w.page.evaluate.return_value=available;w.protocol=Mock();w.focus=Mock();w.select=Mock()
            before=snapshot('AéB',2,3);before['focused']=False;w.snapshot=Mock(return_value=({},before))
            with self.assertRaises(Refused) as caught:w.type('t','x','insert')
            self.assertEqual(caught.exception.code,'UNSUPPORTED_TEXT_BOUNDARY' if available is False else 'TEXT_BOUNDARY_UNAVAILABLE')
            self.assertEqual(w.effect,'none');w.focus.assert_not_called();w.select.assert_not_called();w.protocol.send.assert_not_called()

    def test_selected_deletion_refuses_before_focus_or_input(self):
        w=Worker('unused');w.page=Mock();w.page.evaluate.return_value=False;w.protocol=Mock();w.focus=Mock()
        before=snapshot('A👩🏽‍💻B',2,4);before['focused']=False;w.snapshot=Mock(return_value=({},before))
        with self.assertRaises(Refused) as caught:w.type('t','','insert')
        self.assertEqual(caught.exception.code,'UNSUPPORTED_TEXT_BOUNDARY')
        self.assertEqual(w.effect,'none');w.focus.assert_not_called();w.protocol.send.assert_not_called()

    def test_whole_field_edges_do_not_require_segmenter(self):
        w=Worker('unused');w.page=Mock();w.require_text_boundaries('é',0,2);w.page.evaluate.assert_not_called()

    def test_only_explicit_true_boundary_result_is_accepted(self):
        w=Worker('unused');w.page=Mock()
        for result in ('true',1,{},False):
            w.page.evaluate.return_value=result
            with self.assertRaises(Refused):w.require_text_boundaries('éx',1,2)
