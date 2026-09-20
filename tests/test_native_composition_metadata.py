"""Unknown preedit evidence must coexist with exact exposed-text readback."""
import json,unittest
from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import Mock,patch
from luda.desktop import Desktop
from luda.common import DesktopError
from luda.timing import elapsed_time
from luda import server

class NativeCompositionTests(unittest.TestCase):
    def desktop(self):
        d=Desktop.__new__(Desktop)
        node={'start':'start','interfaces':['Text','EditableText'],'states':['editable']}
        d.elements={'field':{'time':elapsed_time(),'window_id':'window','node':node}}
        d.target_window=Mock(return_value={'pid':42,'start':'start'})
        d.ax=Mock(return_value={'text':'BASE','characters':4,'truncated':False})
        return d
    def test_native_read_adds_unknown_not_inactive_without_extra_input(self):
        d=self.desktop();result=d.element('field','read')
        self.assertEqual(result['text'],'BASE')
        self.assertEqual(result['composition'],{'known':False,'active':None})
        self.assertEqual(d.ax.call_count,1)
        self.assertFalse(d.ax.call_args.args[1])
        self.assertNotIn('composition',d.ax.return_value)
    def test_exact_native_insert_and_replace_still_verify_only_exposed_text(self):
        for mode in ('insert','replace'):
            d=self.desktop();d.ax.return_value={'effect':'verified','exact_match':True,'actual_characters':5,'expected_characters':5}
            result=d.type_text('field','value',mode=mode)
            self.assertTrue(result['exact_match']);self.assertEqual(result['effect'],'verified')
            self.assertEqual(result['composition'],{'known':False,'active':None})
            self.assertIn('pending IME composition and application commit are not verified',result['verification'])
            self.assertEqual(d.ax.call_count,1)
    def test_cooperating_browser_known_state_is_not_overwritten(self):
        for composition in ({'known':True,'active':False},{'known':True,'active':True},{'known':False,'active':None}):
            d=self.desktop();d.elements['field']['provider']='owned_browser'
            result={'text':'current','composition':composition};d.browser=SimpleNamespace(element=Mock(return_value=result))
            self.assertIs(d.element('field','read'),result)
            self.assertIs(d.type_text('field','value'),result)
            d.ax.assert_not_called()
    def test_protected_read_refusal_does_not_create_readback(self):
        d=self.desktop();d.ax.side_effect=DesktopError('PROTECTED_FIELD','Protected contents cannot be read.')
        with self.assertRaises(DesktopError) as caught:d.element('field','read')
        self.assertEqual(caught.exception.effect,'none')
        self.assertNotIn('composition',caught.exception.details)
    def test_verified_native_clipboard_fallback_also_reports_unknown(self):
        d=self.desktop();d.elements['field']['node']['interfaces']=['Text']
        before={'text':'BASE','truncated':False,'caret_offset':4,'selections':[]}
        after={**before,'text':'BASEX','caret_offset':5}
        d.element=Mock(side_effect=[{'effect':'verified'},before,before,after]);d.paste=Mock()
        result=d.type_text('field','X')
        self.assertTrue(result['exact_match']);self.assertEqual(result['composition'],{'known':False,'active':None})
        d.paste.assert_called_once_with('window','X', _activate=False)
    def test_actual_public_read_projection_preserves_null_and_text(self):
        d=self.desktop()
        backend=SimpleNamespace(control=SimpleNamespace(require_active=lambda:None),transaction=nullcontext,require_supported_backend=lambda:None,element=d.element)
        with patch.object(server,'get_backend',return_value=backend):
            response=server.execute('element','field','read',limit=20)
        value=json.loads(response.content[0].text)
        self.assertFalse(response.isError);self.assertEqual(value['text'],'BASE')
        self.assertEqual(value['composition'],{'known':False,'active':None})
