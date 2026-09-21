"""Successful choose feedback scopes proof without changing semantic actions."""
import unittest
from unittest.mock import Mock, patch

from luda.common import DesktopError, elapsed_time
from luda.desktop import Desktop
from test_semantic import SelectionProvider, w


class SelectionFeedback(unittest.TestCase):
    def driver(self, result=None):
        desktop = Desktop.__new__(Desktop)
        desktop.elements = {'item': {'time': elapsed_time(), 'window_id': 'window',
                                    'node': {'start': 'start'}}}
        desktop.target_window = Mock(return_value={'pid': 1, 'start': 'start', 'active': True})
        desktop.ax = Mock(return_value=result)
        desktop.activate = Mock()
        desktop.browser = Mock()
        return desktop

    def assert_selection_only(self, result):
        self.assertEqual(result['verification_scope'], 'selection')
        self.assertIsInstance(result['next_step'], str)
        self.assertTrue(result['next_step'].strip())

    def test_all_provider_receipts_keep_existing_fields_and_scope_their_proof(self):
        receipts = [
            {'selected': True, 'changed': True},  # ordinary list
            {'checked': True, 'changed': True},  # radio uses check internally
            {'selected': True, 'selection_method': 'combo_option_activation'},
            {'selected': True, 'selection_method': 'advertised_toggle_actions'},
            {'selected': True, 'selection_scope': 'table_row'},
            {'selected': True, 'selection_scope': 'table_row_range', 'selected_items': []},
            {'selected': True, 'selection_scope': 'list_item_range', 'selected_items': []},
        ]
        for receipt in receipts:
            for changed in (True, False):
                with self.subTest(receipt=receipt, changed=changed):
                    original = {'effect': 'verified', 'accepted': True, **receipt, 'changed': changed}
                    desktop = self.driver(original)
                    result = desktop.element('item', 'choose')
                    self.assert_selection_only(result)
                    self.assertEqual({k: result[k] for k in original}, original)
                    self.assertNotIn('verification_scope', original)
                    desktop.ax.assert_called_once()
                    self.assertEqual(desktop.ax.call_args.args[0]['op'], 'choose')
                    desktop.activate.assert_not_called()

    def test_real_list_provider_changed_and_unchanged_never_activate(self):
        parent = SelectionProvider()
        node = parent.nodes[1]
        node.get_parent = lambda: parent
        node.get_action_iface = Mock(side_effect=AssertionError('Selection must not activate'))
        current = {'protected': False, 'role': 'list item', 'states': [], 'name': node.get_name(),
                   'name_fingerprint': w.bounded_name_identity(node, False)[1]}
        desktop = self.driver()
        desktop.ax.side_effect = lambda request, mutation: w.semantic(node, current, request)
        with patch.object(w.Atspi, 'Selection', SelectionProvider, create=True), \
                patch.object(w, 'states_of', return_value={'sensitive', 'showing'}), \
                patch.object(w, 'verify', lambda predicate: predicate()):
            for changed in (True, False):
                result = desktop.element('item', 'choose')
                self.assertEqual(result['changed'], changed)
                self.assertEqual(parent.selected, {1})
                self.assert_selection_only(result)
        node.get_action_iface.assert_not_called()
        desktop.activate.assert_not_called()

    def test_uncertain_and_dispatched_receipts_do_not_claim_verified_selection(self):
        for effect in ('uncertain', 'dispatched', 'none'):
            original = {'effect': effect, 'accepted': True, 'selected': False}
            desktop = self.driver(original)
            self.assertEqual(desktop.element('item', 'choose'), original)
            desktop.ax.assert_called_once()
            desktop.activate.assert_not_called()

    def test_timeout_or_stale_refusal_is_not_rewritten_or_retried(self):
        for code, effect in (('TIMEOUT', 'uncertain'), ('STALE_TARGET', 'none')):
            desktop = self.driver()
            failure = DesktopError(code, 'fixture', effect=effect)
            desktop.ax.side_effect = failure
            with self.assertRaises(DesktopError) as caught:
                desktop.element('item', 'choose')
            self.assertIs(caught.exception, failure)
            desktop.ax.assert_called_once()
            desktop.activate.assert_not_called()

    def test_other_operations_keep_their_existing_verification(self):
        original = {'effect': 'verified', 'checked': True}
        desktop = self.driver(original)
        self.assertEqual(desktop.element('item', 'check', checked=True), original)

    def test_owned_provider_success_uses_same_feedback_boundary(self):
        desktop = self.driver()
        desktop.elements['item']['provider'] = 'owned_browser'
        desktop.browser.element.return_value = {'effect': 'verified', 'selected': True, 'changed': False}
        self.assert_selection_only(desktop.element('item', 'choose'))
        desktop.ax.assert_not_called()
        desktop.browser.element.assert_called_once()

    def test_owned_provider_refusal_is_preserved(self):
        desktop = self.driver()
        desktop.elements['item']['provider'] = 'owned_browser'
        desktop.browser.element.side_effect = DesktopError('UNSUPPORTED_ACTION', 'fixture')
        with self.assertRaises(DesktopError) as caught:
            desktop.element('item', 'choose')
        self.assertEqual(caught.exception.code, 'UNSUPPORTED_ACTION')
        desktop.ax.assert_not_called()


if __name__ == '__main__':
    unittest.main()
