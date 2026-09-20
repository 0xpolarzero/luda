import unittest
from unittest.mock import Mock
from test_browser_rich import value
from luda._browser_worker import Worker,Refused
from luda.common import DesktopError


def selected(text,start,end,marks=None):
    v=value(text,marks);v.update(start=start,end=end,selection={'start':start,'end':end});return v


class RichClipboardTests(unittest.TestCase):
    def worker(self,values):
        w=Worker('unused');w.clipboard=Mock();w.clipboard.stage.side_effect=lambda text,publishing:publishing();w.native_target={'xid':1,'generation':'bound'}
        w.focus=Mock();w.protocol=Mock();w.snapshot=Mock(side_effect=[({},v) if isinstance(v,dict) else v for v in values]);return w

    def test_preflight_budget_and_policy_do_not_focus_or_stage(self):
        for text,policy in [('x\ny',None),('\n'*27,'paragraph')]:
            before=selected('abc',1,2);before['focused']=False;w=self.worker([])
            with self.assertRaises(Refused):w.rich_clipboard_type('t',text,'insert',policy,before)
            w.focus.assert_not_called();w.clipboard.stage.assert_not_called();self.assertEqual(w.effect,'none')

    def test_predicted_paragraph_overflow_preserves_input_and_clipboard(self):
        before=selected('\n'*127,127,127);w=self.worker([])
        with self.assertRaises(Refused) as exc:w.rich_clipboard_type('t','\n','insert','paragraph',before)
        self.assertEqual(exc.exception.code,'VERIFICATION_LIMIT');w.clipboard.preflight.assert_not_called();w.focus.assert_not_called()

    def test_html_fields_do_not_opt_into_clipboard(self):
        before=selected('abc',1,2);before['tag']='TEXTAREA';w=self.worker([before])
        with self.assertRaises(Refused) as exc:w.type('t','x','insert',transport='clipboard')
        self.assertEqual(exc.exception.code,'UNSUPPORTED_ACTION');w.clipboard.stage.assert_not_called()

    def test_storage_failure_before_publication_has_no_clipboard_effect(self):
        before=selected('abc',1,2);w=self.worker([before,before])
        w.clipboard.stage.side_effect=DesktopError('STORAGE_UNAVAILABLE','fixed')
        with self.assertRaises(Refused) as exc:w.rich_clipboard_type('t','x','insert',None,before)
        self.assertEqual(exc.exception.code,'STORAGE_UNAVAILABLE');self.assertFalse(w.clipboard_changed);self.assertEqual(w.effect,'none');w.protocol.send.assert_not_called()

    def test_model_change_during_native_plan_prevents_virtual_input(self):
        before=selected('abc',1,2);changed=selected('NEW',1,2);w=self.worker([before,before,before,changed])
        with self.assertRaises(Refused) as exc:w.rich_clipboard_type('t','x','insert',None,before)
        self.assertEqual(exc.exception.code,'TEXT_CHANGED');w.clipboard.prepare_key.assert_called_once();w.protocol.send.assert_not_called();self.assertTrue(w.clipboard_changed)

    def test_model_change_during_deletion_plan_prevents_input_with_none_effect(self):
        before=selected('abc',1,2);changed=selected('NEW',1,2);w=self.worker([before,before,changed])
        with self.assertRaises(Refused) as exc:w.rich_clipboard_type('t','','insert',None,before)
        self.assertEqual(exc.exception.code,'TEXT_CHANGED');w.protocol.send.assert_not_called();self.assertEqual(w.effect,'none')

    def test_held_input_is_refused_before_focus_and_clipboard(self):
        before=selected('abc',1,2);before['focused']=False;w=self.worker([])
        w.clipboard.preflight.side_effect=DesktopError('INPUT_HELD','fixed')
        with self.assertRaises(Refused) as exc:w.rich_clipboard_type('t','x','insert',None,before)
        self.assertEqual(exc.exception.code,'INPUT_HELD');w.focus.assert_not_called();w.clipboard.stage.assert_not_called()

    def test_same_length_model_change_after_staging_sends_no_shortcut(self):
        before=selected('abc',1,2);changed=selected('NEW',1,2);w=self.worker([before,before,changed])
        with self.assertRaises(Refused) as exc:w.rich_clipboard_type('t','x','insert',None,before)
        self.assertEqual(exc.exception.code,'TEXT_CHANGED');w.clipboard.prepare_key.assert_not_called();self.assertTrue(w.clipboard_changed);self.assertEqual(w.effect,'uncertain')

    def test_replaced_clipboard_owner_is_not_pasted(self):
        before=selected('abc',1,2);w=self.worker([before,before,before]);w.clipboard.verify.side_effect=DesktopError('CLIPBOARD_CHANGED','fixed')
        with self.assertRaises(Refused) as exc:w.rich_clipboard_type('t','x','insert',None,before)
        self.assertEqual(exc.exception.code,'CLIPBOARD_CHANGED');w.clipboard.prepare_key.assert_not_called();self.assertEqual(w.effect,'uncertain')

    def test_focus_loss_after_first_segment_never_sends_remainder(self):
        before=selected('abc',1,2);w=self.worker([before,before,before,before,Refused('FOCUS_CHANGED')])
        with self.assertRaises(Refused):w.rich_clipboard_type('t','x\ny','insert','paragraph',before)
        self.assertEqual(w.clipboard.stage.call_count,1);self.assertEqual(w.clipboard.stage.call_args.args[0],'x');w.clipboard.prepare_key.assert_called_once();self.assertEqual(w.effect,'uncertain');self.assertEqual(w.protocol.send.call_count,2)

    def test_suffix_marks_changed_after_exact_text_is_not_verified(self):
        before=selected('abc',1,2,[{'type':'strong'}]);after=selected('axc',2,2)
        w=self.worker([before,before,before,before,after])
        with self.assertRaises(Refused) as exc:w.rich_clipboard_type('t','x','insert',None,before)
        self.assertEqual(exc.exception.code,'FORMATTING_CHANGED');w.clipboard.prepare_key.assert_called_once()

    def test_success_explains_application_defined_new_marks(self):
        marks=[{'type':'strong'}]
        before=selected('abc',1,2,marks);after=selected('axc',2,2,marks)
        w=self.worker([before,before,before,before,after])
        result=w.rich_clipboard_type('t','x','insert',None,before)
        self.assertEqual(result['existing_formatting'],'preserved')
        self.assertEqual(result['model'],after['model'])
        self.assertEqual(result['verification'],'Exact paragraph text, structure and unaffected existing marks; new formatting follows application behavior. Application commit is separate.')
        self.assertTrue(result['exact_match'])

    def test_empty_selected_text_deliberately_deletes_without_clipboard(self):
        before=selected('abc',1,2);after=selected('ac',1,1);w=self.worker([before,before,before,after])
        result=w.rich_clipboard_type('t','','insert',None,before)
        self.assertTrue(result['exact_match']);self.assertFalse(result['clipboard_changed']);w.clipboard.stage.assert_not_called()
        w.clipboard.prepare_key.assert_called_once_with(w.native_target,'BackSpace')

    def test_collapsed_empty_text_is_a_noop(self):
        before=selected('abc',1,1);w=self.worker([before]);result=w.rich_clipboard_type('t','','insert',None,before)
        self.assertEqual(result['effect'],'none');w.clipboard.stage.assert_not_called();w.clipboard.prepare_key.assert_not_called()


class ClipboardOwnerTests(unittest.TestCase):
    def test_missing_dependency_fails_before_keyboard_probe(self):
        from unittest.mock import patch
        from luda._browser_clipboard import Clipboard
        with patch('luda._browser_clipboard.shutil.which',return_value=None),patch('luda._browser_clipboard.keyboard_capabilities') as keyboard:
            with self.assertRaises(DesktopError) as caught:Clipboard('unused').preflight()
            self.assertEqual(caught.exception.code,'DEPENDENCY_MISSING');keyboard.assert_not_called()

    def test_existing_owner_exit_refuses_verify_without_clipboard_read(self):
        from unittest.mock import patch
        from luda._browser_clipboard import Clipboard
        c=Clipboard('unused');c.owner=Mock();c.owner.poll.return_value=0
        with patch('luda._browser_clipboard.run') as read:
            with self.assertRaises(DesktopError) as caught:c.verify('payload')
            self.assertEqual(caught.exception.code,'CLIPBOARD_CHANGED');read.assert_not_called()

    def test_latched_input_is_not_cleared_implicitly(self):
        from unittest.mock import patch
        from luda._browser_clipboard import Clipboard
        with patch('luda._browser_clipboard.shutil.which',return_value='/usr/bin/xclip'),patch('luda._browser_clipboard.keyboard_capabilities',return_value={'available':True,'latched_input':True}):
            with self.assertRaises(DesktopError) as caught:Clipboard('unused').preflight()
            self.assertEqual(caught.exception.code,'UNSUPPORTED_INPUT_STATE')


    def test_staging_disk_failure_preserves_existing_owner(self):
        import errno
        from unittest.mock import patch
        from luda._browser_clipboard import Clipboard
        c=Clipboard('unused');c.owner=Mock();publishing=Mock()
        with patch('luda._browser_clipboard.staged_payload',side_effect=OSError(errno.ENOSPC,'synthetic')),patch('luda._browser_clipboard.stop_process') as stop:
            with self.assertRaises(DesktopError) as caught:c.stage('payload',publishing)
            self.assertEqual(caught.exception.code,'STORAGE_UNAVAILABLE');self.assertEqual(caught.exception.effect,'none')
            publishing.assert_not_called();stop.assert_not_called()
