"""Background semantics and foreground fallback without replaying uncertain input."""
import unittest
from unittest.mock import Mock, patch
from luda.common import DesktopError, elapsed_time
from luda.desktop import Desktop


class BackgroundRouting(unittest.TestCase):
    def driver(self):
        d = Desktop.__new__(Desktop)
        d.elements = {'field': {'time': elapsed_time(), 'window_id': 'window',
            'node': {'start': 'start', 'interfaces': ['Text', 'EditableText', 'Component'],
                     'states': ['editable'], 'actions': ['click']}}}
        d.target_window = Mock(return_value={'window_id': 'window:token', 'pid': 1,
                                            'start': 'start', 'xid': 2, 'active': False})
        d.activate = Mock()
        d.agent_feedback = Mock()
        d.ax = Mock(return_value={'effect': 'verified', 'exact_match': True})
        return d

    def test_native_mutations_address_background_without_activation(self):
        for op, args in [('set', {'text': 'hello'}), ('insert', {'text': 'hello'}),
                         ('invoke', {}), ('check', {'checked': True}),
                         ('value', {'value': 2}), ('select', {'start_offset': 0, 'end_offset': 0}),
                         ('secret', {'text': 'fixture'})]:
            with self.subTest(op=op):
                d = self.driver()
                d.element('field', op, **args)
                d.target_window.assert_called_once_with('window', False)
                d.activate.assert_not_called()
                d.ax.assert_called_once()
                d.agent_feedback.assert_called_once_with('window', element_id='field')

    def test_native_typing_uses_background_text_provider(self):
        d = self.driver()
        d.type_text('field', 'hello', 'replace')
        d.activate.assert_not_called()
        self.assertEqual(d.ax.call_args.args[0]['op'], 'set')

    def test_focus_and_key_activate_automatically(self):
        d = self.driver()
        d.element('field', 'focus')
        d.activate.assert_called_once_with('window')
        d = self.driver()
        with patch('luda.desktop.send_chord', return_value={'effect': 'dispatched'}) as send:
            d.key('window', 'Return')
        d.activate.assert_called_once_with('window')
        d.target_window.assert_called_with('window')
        send.assert_called_once_with('Return', 2, target_generation='token', count=1)

    def test_invalid_requests_do_not_activate_or_display_action(self):
        for action in [lambda d: d.key('window', 'not a chord'),
                       lambda d: d.element('field', 'invoke', action='absent'),
                       lambda d: d.type_text('field', 'hello', 'invalid'),
                       lambda d: d.paste('window', 'hello', 'invalid'),
                       lambda d: d.paste('window', '')]:
            d = self.driver()
            try: action(d)
            except DesktopError: pass
            d.activate.assert_not_called()
            d.agent_feedback.assert_not_called()
            d.ax.assert_not_called()

    def test_timeout_or_uncertain_effect_never_activates_or_replays(self):
        for code in ('TIMEOUT', 'ACCESSIBILITY_ERROR', 'FOCUS_CHANGED'):
            d = self.driver()
            d.ax.side_effect = DesktopError(code, 'failed', effect='uncertain')
            with self.assertRaises(DesktopError): d.element('field', 'invoke')
            d.ax.assert_called_once()
            d.activate.assert_not_called()

    def test_activation_failure_sends_no_key(self):
        d = self.driver()
        d.activate.side_effect = DesktopError('ACTIVATION_FAILED', 'failed', effect='uncertain')
        with patch('luda.desktop.send_chord') as send, self.assertRaises(DesktopError):
            d.key('window', 'Return')
        send.assert_not_called()

    def test_focus_race_after_activation_does_not_send_or_retry(self):
        d = self.driver()
        d.target_window.side_effect = [d.target_window.return_value,
                                      DesktopError('FOCUS_CHANGED', 'lost focus')]
        with patch('luda.desktop.send_chord') as send, self.assertRaises(DesktopError):
            d.key('window', 'Return')
        d.activate.assert_called_once()
        send.assert_not_called()

    def test_paste_activates_before_clipboard_work_and_does_not_reacquire(self):
        d = self.driver()
        d.runtime = None
        with patch('luda.desktop.staged_payload', side_effect=RuntimeError('staging reached')) as stage:
            with self.assertRaises(RuntimeError): d.paste('window', 'hello')
        d.activate.assert_called_once_with('window')
        stage.assert_called_once()

    def test_composed_input_does_not_activate_after_losing_focus(self):
        for operation in ('key', 'paste'):
            d = self.driver()
            d.target_window.side_effect = DesktopError('FOCUS_CHANGED', 'lost focus')
            with patch('luda.desktop.send_chord') as send, self.assertRaises(DesktopError):
                if operation == 'key': d.key('window', 'BackSpace', _activate=False)
                else: d.paste('window', 'hello', _activate=False)
            d.activate.assert_not_called()
            send.assert_not_called()

    def test_owned_browser_selection_focus_is_automatic_after_validation(self):
        from luda._browser_worker import Worker, Refused
        before = {'text': 'hello', 'focused': False, 'start': 0, 'end': 0}
        focused = {**before, 'focused': True}
        after = {**focused, 'start': 1, 'end': 3}
        w = Worker('unused')
        node = Mock()
        w.snapshot = Mock(side_effect=[({'node': node}, before), ({}, focused), ({}, after)])
        w.focus = Mock()
        self.assertEqual(w.select('token', 1, 3)['effect'], 'verified')
        w.focus.assert_called_once_with('token')
        node.evaluate.assert_called_once()
        w.snapshot = Mock(return_value=({'node': node}, before))
        w.focus.reset_mock()
        with self.assertRaises(Refused): w.select('token', -1, 3)
        w.focus.assert_not_called()

    def test_no_effect_background_focus_refusal_retries_once_in_foreground(self):
        for code in ('FOCUS_CHANGED', 'NOT_INTERACTABLE'):
            d = self.driver()
            d.ax.side_effect = [DesktopError(code, 'preflight refusal', details={'foreground_required': True}), {'effect': 'dispatched'}]
            self.assertEqual(d.element('field', 'invoke')['effect'], 'dispatched')
            d.activate.assert_called_once_with('window')
            self.assertEqual(d.ax.call_count, 2)

    def test_hidden_background_target_still_refuses_after_one_foreground_try(self):
        d = self.driver()
        d.ax.side_effect = DesktopError('NOT_INTERACTABLE', 'hidden', details={'foreground_required': True})
        with self.assertRaises(DesktopError) as caught: d.element('field', 'invoke')
        self.assertEqual(caught.exception.effect, 'uncertain')
        self.assertEqual(d.ax.call_count, 2)
        d.activate.assert_called_once()

    def test_direct_key_and_focus_errors_include_prior_activation(self):
        for code in ('STALE_TARGET', 'INPUT_HELD', 'UNSUPPORTED', 'TIMEOUT'):
            for operation in ('key', 'focus'):
                with self.subTest(code=code, operation=operation):
                    d = self.driver()
                    with patch('luda.desktop.keyboard_capabilities', return_value={'input_held': False}), patch('luda.desktop.send_chord', side_effect=DesktopError(code, 'refused')):
                        d.ax.side_effect = DesktopError(code, 'refused')
                        with self.assertRaises(DesktopError) as caught:
                            if operation == 'key': d.key('window', 'Return')
                            else: d.element('field', 'focus')
                    self.assertEqual(caught.exception.effect, 'uncertain')
                    d.activate.assert_called_once()

    def test_held_input_before_activation_has_no_effect(self):
        for operation in ('key', 'focus', 'paste'):
            d = self.driver()
            with patch('luda.desktop.keyboard_capabilities', return_value={'input_held': True}):
                with self.assertRaises(DesktopError) as caught:
                    if operation == 'key': d.key('window', 'Return')
                    elif operation == 'focus': d.element('field', 'focus')
                    else: d.paste('window', 'hello')
            self.assertEqual(caught.exception.code, 'INPUT_HELD')
            self.assertEqual(caught.exception.effect, 'none')
            d.activate.assert_not_called()

    def test_paste_failure_after_activation_includes_prior_effect(self):
        d = self.driver()
        d.runtime = None
        with patch('luda.desktop.keyboard_capabilities', return_value={'input_held': False}), patch('luda.desktop.staged_payload', side_effect=DesktopError('STALE_TARGET', 'refused')):
            with self.assertRaises(DesktopError) as caught: d.paste('window', 'hello')
        self.assertEqual(caught.exception.effect, 'uncertain')
        d.activate.assert_called_once()

    def test_disabled_or_offscreen_refusal_does_not_activate(self):
        for reason in ('disabled', 'offscreen'):
            d = self.driver()
            d.ax.side_effect = DesktopError('NOT_INTERACTABLE', reason)
            with self.assertRaises(DesktopError) as caught:
                d.element('field', 'invoke')
            self.assertEqual(caught.exception.effect, 'none')
            d.activate.assert_not_called()
            d.ax.assert_called_once()

    def test_only_literal_foreground_marker_allows_fallback(self):
        for value in (False, None, 'true', 1):
            d = self.driver()
            d.ax.side_effect = DesktopError('NOT_INTERACTABLE', 'refused', details={'foreground_required': value})
            with self.assertRaises(DesktopError): d.element('field', 'invoke')
            d.activate.assert_not_called()
            d.ax.assert_called_once()
