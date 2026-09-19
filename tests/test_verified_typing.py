import time
import unittest
from unittest.mock import Mock
from luda.common import DesktopError
from luda.desktop import Desktop


class VerifiedTyping(unittest.TestCase):
    def make(self):
        d=object.__new__(Desktop)
        d.elements={'e':{'time':time.monotonic(),'window_id':'w','node':{'interfaces':['Text'],'states':['editable'],'protected':False}}}
        d.paste=Mock();d.key=Mock()
        return d
    def value(self,text,caret=1,selection=None):
        return {'text':text,'caret_offset':caret,'selections':selection or [],'characters':len(text),'truncated':False}
    def test_missing_editable_text_uses_verified_clipboard(self):
        d=self.make()
        d.element=Mock(side_effect=[{'effect':'verified'},self.value('AZ'),self.value('AZ'),self.value('A👩🏽\u200d💻\nZ',6)])
        result=d.type_text('e','👩🏽\u200d💻\n')
        self.assertEqual(result['effect'],'verified');self.assertTrue(result['caret_verified'])
        d.paste.assert_called_once_with('w','👩🏽\u200d💻\n')
    def test_selection_change_prevents_paste(self):
        d=self.make();d.element=Mock(side_effect=[{'effect':'verified'},self.value('AZ'),self.value('AZ',2)])
        with self.assertRaises(DesktopError) as error:d.type_text('e','x')
        self.assertEqual(error.exception.code,'TEXT_CHANGED');d.paste.assert_not_called()
    def test_missing_focus_prevents_paste(self):
        d=self.make();d.element=Mock(return_value={'effect':'dispatched'})
        with self.assertRaises(DesktopError) as error:d.type_text('e','x')
        self.assertEqual(error.exception.code,'FOCUS_UNVERIFIED');d.paste.assert_not_called()
    def test_no_retry_after_semantic_mutation_failure(self):
        d=self.make();d.elements['e']['node']['interfaces'].append('EditableText')
        d.element=Mock(side_effect=DesktopError('TIMEOUT','provider stalled',effect='uncertain'))
        with self.assertRaises(DesktopError):d.type_text('e','x')
        d.paste.assert_not_called()
    def test_protected_field_refused_before_mutation(self):
        d=self.make();d.elements['e']['node']['protected']=True;d.element=Mock()
        with self.assertRaises(DesktopError):d.type_text('e','secret')
        d.element.assert_not_called();d.paste.assert_not_called()
